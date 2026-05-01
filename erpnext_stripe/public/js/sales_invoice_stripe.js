frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 1) return;
		if (!["Unpaid", "Overdue", "Partly Paid"].includes(frm.doc.status)) return;

		frm.add_custom_button(__("Charge via Stripe"), () => {
			frappe.confirm(
				__("Charge {0} via Stripe now using the customer's default card?", [frm.doc.name]),
				() => {
					frappe.call({
						method: "erpnext_stripe.api.payment_intent.charge_invoice",
						args: { sales_invoice: frm.doc.name },
						freeze: true,
						freeze_message: __("Contacting Stripe…"),
						callback(r) {
							if (r.message) {
								frappe.show_alert({
									message: __("Payment initiated — Log: {0}", [r.message.log]),
									indicator: "green",
								});
								frm.reload_doc();
							}
						},
					});
				}
			);
		}, __("Stripe"));
	},
});
