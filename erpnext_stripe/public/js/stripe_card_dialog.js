// Shared card-setup actions, used by both the Stripe Customer form and the
// Stripe section on the Customer form. Loaded desk-wide via app_include_js so
// a Customer with no Stripe record yet can still reach them.
frappe.provide("erpnext_stripe");

Object.assign(erpnext_stripe, {
	/**
	 * Make sure the customer has a Stripe Customer record, then hand its name
	 * to `callback`. Creates one at Stripe on first use — hence the confirm.
	 */
	with_stripe_customer(customer, callback) {
		frappe.call({
			method: "erpnext_stripe.api.sync.get_stripe_account_options",
			callback(r) {
				const options = r.message || [];
				if (!options.length) {
					frappe.msgprint(__("No Stripe Settings configured."));
					return;
				}
				const proceed = (stripe_settings) =>
					erpnext_stripe._provision(customer, stripe_settings, callback);

				const preferred = options.find((o) => o.is_default);
				if (options.length === 1 || preferred) {
					const chosen = preferred || options[0];
					frappe.confirm(
						__("Set up {0} on the {1} Stripe account ({2})?", [
							customer,
							chosen.name,
							chosen.mode,
						]),
						() => proceed(chosen.name)
					);
					return;
				}
				frappe.prompt(
					[{
						fieldname: "stripe_settings",
						fieldtype: "Select",
						label: __("Stripe Account"),
						options: options.map((o) => o.name).join("\n"),
						reqd: 1,
					}],
					(v) => proceed(v.stripe_settings),
					__("Select Stripe Account")
				);
			},
		});
	},

	_provision(customer, stripe_settings, callback) {
		frappe.call({
			method: "erpnext_stripe.api.sync.ensure_stripe_customer",
			args: { customer, stripe_settings },
			freeze: true,
			freeze_message: __("Setting up Stripe…"),
			callback(r) {
				if (!r.message) return;
				const { stripe_customer, status } = r.message;
				if (status === "created") {
					frappe.show_alert({ message: __("Stripe customer created"), indicator: "green" });
				} else if (status === "adopted") {
					frappe.show_alert({
						message: __("Linked to the existing Stripe customer on this email"),
						indicator: "blue",
					});
				}
				callback(stripe_customer, r.message);
			},
		});
	},

	load_stripe_js() {
		if (window.Stripe) return Promise.resolve();
		return new Promise((resolve, reject) => {
			const script = document.createElement("script");
			script.src = "https://js.stripe.com/v3/";
			script.onload = () => resolve();
			script.onerror = () => reject(new Error("stripe.js failed to load"));
			document.head.appendChild(script);
		});
	},

	/**
	 * Agent-entered card. The fields are a Stripe iframe, so the card number
	 * goes straight to Stripe and never reaches ERPNext.
	 */
	add_card(stripe_customer, on_saved) {
		frappe.call({
			method: "erpnext_stripe.api.setup_intent.create_setup_intent",
			args: { stripe_customer },
			freeze: true,
			freeze_message: __("Contacting Stripe…"),
			callback(r) {
				if (!r.message) return;
				erpnext_stripe
					.load_stripe_js()
					.then(() => erpnext_stripe._mount_dialog(stripe_customer, r.message, on_saved))
					.catch(() => {
						frappe.msgprint({
							title: __("Stripe unavailable"),
							message: __("Could not load Stripe.js. Check this browser's network access to js.stripe.com."),
							indicator: "red",
						});
					});
			},
		});
	},

	_mount_dialog(stripe_customer, ctx, on_saved) {
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
				args: { stripe_customer },
				freeze: true,
				freeze_message: __("Saving card…"),
				callback() {
					frappe.show_alert({ message: __("Card added"), indicator: "green" });
					if (on_saved) on_saved();
				},
			});
		}
	},

	email_setup_link(customer, stripe_settings) {
		frappe.confirm(
			__("Email {0} a link to add their own card?", [customer]),
			() => {
				frappe.call({
					method: "erpnext_stripe.api.setup_intent.send_card_setup_email",
					args: { customer, stripe_settings },
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
	},

	copy_setup_link(stripe_customer) {
		frappe.call({
			method: "erpnext_stripe.api.setup_intent.get_card_setup_link",
			args: { stripe_customer },
			freeze: true,
			callback(r) {
				if (!r.message) return;
				const { url, expires_in_hours } = r.message;
				// Shown as well as copied: clipboard writes are blocked in some
				// browsers, and the agent may want to paste it by hand.
				frappe.utils.copy_to_clipboard(url);
				frappe.msgprint({
					title: __("Card Setup Link"),
					message: `<p>${__("Copied to clipboard. Valid for {0} hours.", [expires_in_hours])}</p>
						<pre style="white-space: pre-wrap; word-break: break-all;">${frappe.utils.escape_html(url)}</pre>`,
					indicator: "blue",
				});
			},
		});
	},
});
