frappe.ui.form.on("Stripe Customer", {
	refresh(frm) {
		if (!frm.is_new()) {
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

			frm.add_custom_button(__("Add Card"), () => {
				frappe.call({
					method: "erpnext_stripe.api.setup_intent.create_setup_intent",
					args: { stripe_customer: frm.doc.name },
					callback(r) {
						if (r.message) {
							window.open(
								`/add-card?stripe_customer=${frm.doc.name}&client_secret=${r.message.client_secret}`,
								"_blank"
							);
						}
					},
				});
			});
		}
	},
});
