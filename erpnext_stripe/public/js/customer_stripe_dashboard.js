frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new()) return;
		_render_stripe_section(frm);
	},
});

function _render_stripe_section(frm) {
	frappe.call({
		method: "erpnext_stripe.api.sync.get_customer_stripe_summary",
		args: { customer: frm.doc.name },
		callback(r) {
			const records = r.message || [];
			if (!records.length) {
				_render_empty_state(frm);
				return;
			}
			_render_stripe_cards(frm, records);
		},
	});
}

function _render_empty_state(frm) {
	frm.dashboard.add_section(
		`<div class="stripe-section">
			<p class="text-muted">${__("No Stripe customer linked.")}</p>
		</div>`,
		__("Stripe")
	);
	frm.dashboard.add_indicator(__("No Stripe Customer"), "grey");
}

function _render_stripe_cards(frm, records) {
	let html = `<div class="stripe-section">`;

	for (const rec of records) {
		const badge = rec.mode === "Test"
			? `<span class="badge badge-warning">${__("Test")}</span>`
			: `<span class="badge badge-success">${__("Live")}</span>`;

		const defaultPm = (rec.payment_methods || []).find((p) => p.is_default);
		const cardLine = defaultPm
			? `${defaultPm.brand.toUpperCase()} •••• ${defaultPm.last4} (${defaultPm.exp_month}/${defaultPm.exp_year})`
			: `<span class="text-muted">${__("No default card")}</span>`;

		html += `
			<div class="row" style="margin-bottom: 8px;">
				<div class="col-xs-6">
					${badge} <strong>${rec.company}</strong><br>
					<small class="text-muted">${rec.stripe_customer_id}</small>
				</div>
				<div class="col-xs-6">
					${cardLine}
				</div>
			</div>`;
	}

	html += `</div>`;

	frm.dashboard.add_section(html, __("Stripe"));

	// Action buttons
	frm.add_custom_button(__("View Stripe Customer"), () => {
		if (records.length === 1) {
			frappe.set_route("Form", "Stripe Customer", records[0].name);
		} else {
			frappe.set_route("List", "Stripe Customer", { customer: frm.doc.name });
		}
	}, __("Stripe"));

	frm.add_custom_button(__("Send Card Setup Link"), () => {
		_with_settings_selection(records, (stripe_settings) => {
			_send_card_setup_email(frm.doc.name, stripe_settings);
		});
	}, __("Stripe"));

	frm.add_custom_button(__("Process Pending Invoices"), () => {
		_with_settings_selection(records, (stripe_settings) => {
			_process_pending_invoices(frm.doc.name, stripe_settings);
		});
	}, __("Stripe"));
}

function _with_settings_selection(records, callback) {
	const options = records.map((r) => r.stripe_settings);
	if (options.length === 1) {
		callback(options[0]);
	} else {
		frappe.prompt(
			[{
				fieldname: "stripe_settings",
				fieldtype: "Select",
				label: __("Stripe Account"),
				options: options.join("\n"),
				reqd: 1,
			}],
			(values) => callback(values.stripe_settings),
			__("Select Stripe Account")
		);
	}
}

function _send_card_setup_email(customer, stripe_settings) {
	frappe.confirm(
		__("Send a card setup email to this customer?"),
		() => {
			frappe.call({
				method: "erpnext_stripe.api.setup_intent.send_card_setup_email",
				args: { customer, stripe_settings },
				callback() {
					frappe.show_alert({ message: __("Card setup email sent"), indicator: "green" });
				},
			});
		}
	);
}

function _process_pending_invoices(customer, stripe_settings) {
	frappe.confirm(
		__("Charge all outstanding invoices for this customer via Stripe?"),
		() => {
			frappe.call({
				method: "erpnext_stripe.api.payment_intent.process_pending_invoices",
				args: { customer, stripe_settings },
				callback(r) {
					if (r.message) {
						const count = r.message.enqueued;
						if (count === 0) {
							frappe.show_alert({ message: __("No outstanding invoices to charge"), indicator: "blue" });
						} else {
							frappe.show_alert({
								message: __("{0} invoice(s) queued for payment", [count]),
								indicator: "green",
							});
						}
					}
				},
			});
		}
	);
}
