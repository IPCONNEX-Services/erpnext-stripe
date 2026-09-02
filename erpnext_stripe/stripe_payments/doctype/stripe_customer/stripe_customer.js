frappe.ui.form.on("Stripe Customer", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Refresh Cards"), () => {
			frappe.call({
				method: "erpnext_stripe.api.setup_intent.refresh_payment_methods",
				args: { stripe_customer: frm.doc.name },
				freeze: true,
				callback() {
					frm.reload_doc();
				},
			});
		});

		// Agent enters the card themselves, in the desk. The fields are a Stripe
		// iframe, so the card number never reaches our server.
		frm.add_custom_button(__("Add Card"), () => _open_add_card_dialog(frm), __("Add Card"));

		// Customer enters it themselves, from a link that expires.
		frm.add_custom_button(__("Email Setup Link to Customer"), () => _email_setup_link(frm), __("Add Card"));
		frm.add_custom_button(__("Copy Setup Link"), () => _copy_setup_link(frm), __("Add Card"));
	},
});

// --- Agent-entered card ----------------------------------------------------

function _open_add_card_dialog(frm) {
	frappe.call({
		method: "erpnext_stripe.api.setup_intent.create_setup_intent",
		args: { stripe_customer: frm.doc.name },
		freeze: true,
		freeze_message: __("Contacting Stripe…"),
		callback(r) {
			if (!r.message) return;
			_load_stripe_js()
				.then(() => _mount_card_dialog(frm, r.message))
				.catch(() => {
					frappe.msgprint({
						title: __("Stripe unavailable"),
						message: __("Could not load Stripe.js. Check this browser's network access to js.stripe.com."),
						indicator: "red",
					});
				});
		},
	});
}

function _load_stripe_js() {
	if (window.Stripe) return Promise.resolve();
	return new Promise((resolve, reject) => {
		const script = document.createElement("script");
		script.src = "https://js.stripe.com/v3/";
		script.onload = () => resolve();
		script.onerror = () => reject(new Error("stripe.js failed to load"));
		document.head.appendChild(script);
	});
}

function _mount_card_dialog(frm, ctx) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Card"),
		fields: [{ fieldtype: "HTML", fieldname: "card_area" }],
		primary_action_label: __("Save Card"),
		primary_action: () => submit(),
	});

	dialog.fields_dict.card_area.$wrapper.html(`
		<p class="text-muted small">
			${__("Card details go straight to Stripe from this form — they are never sent to or stored in ERPNext.")}
		</p>
		<div class="stripe-desk-element" style="min-height: 90px;"></div>
		<div class="text-danger small mt-2 stripe-desk-error" style="display:none;"></div>
	`);
	dialog.show();

	const $error = dialog.$wrapper.find(".stripe-desk-error");
	const stripe = Stripe(ctx.publishable_key);
	const elements = stripe.elements({ clientSecret: ctx.client_secret });
	elements.create("payment").mount(dialog.$wrapper.find(".stripe-desk-element")[0]);

	async function submit() {
		const $btn = dialog.get_primary_btn();
		$btn.prop("disabled", true).text(__("Saving…"));
		$error.hide();

		const { error } = await stripe.confirmSetup({ elements, redirect: "if_required" });

		if (error) {
			$error.text(error.message).show();
			$btn.prop("disabled", false).text(__("Save Card"));
			return;
		}

		dialog.hide();
		frappe.call({
			method: "erpnext_stripe.api.setup_intent.refresh_payment_methods",
			args: { stripe_customer: frm.doc.name },
			freeze: true,
			freeze_message: __("Saving card…"),
			callback() {
				frappe.show_alert({ message: __("Card added"), indicator: "green" });
				frm.reload_doc();
			},
		});
	}
}

// --- Customer-entered card -------------------------------------------------

function _email_setup_link(frm) {
	frappe.confirm(
		__("Email {0} a link to add their own card?", [frm.doc.customer || frm.doc.name]),
		() => {
			frappe.call({
				method: "erpnext_stripe.api.setup_intent.send_card_setup_email",
				args: { customer: frm.doc.customer, stripe_settings: frm.doc.stripe_settings },
				freeze: true,
				callback(r) {
					if (!r.message) return;
					frappe.show_alert({
						message: __("Setup link sent to {0}", [(r.message.recipients || []).join(", ")]),
						indicator: "green",
					});
				},
			});
		}
	);
}

function _copy_setup_link(frm) {
	frappe.call({
		method: "erpnext_stripe.api.setup_intent.get_card_setup_link",
		args: { stripe_customer: frm.doc.name },
		freeze: true,
		callback(r) {
			if (!r.message) return;
			const { url, expires_in_hours } = r.message;
			// Shown as well as copied: clipboard writes are blocked in some
			// browsers, and the agent may want to paste it somewhere by hand.
			frappe.utils.copy_to_clipboard(url);
			frappe.msgprint({
				title: __("Card Setup Link"),
				message: `<p>${__("Copied to clipboard. Valid for {0} hours.", [expires_in_hours])}</p>
					<pre style="white-space: pre-wrap; word-break: break-all;">${frappe.utils.escape_html(url)}</pre>`,
				indicator: "blue",
			});
		},
	});
}
