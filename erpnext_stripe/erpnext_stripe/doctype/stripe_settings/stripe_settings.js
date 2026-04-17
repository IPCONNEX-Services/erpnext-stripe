frappe.ui.form.on("Stripe Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Sync from Stripe"), () => {
			frappe.confirm(
				__("This will sync all customers and payment methods from Stripe. Continue?"),
				() => {
					frappe.call({
						method: "erpnext_stripe.api.sync.sync_from_stripe",
						args: { stripe_settings: frm.doc.name },
						freeze: true,
						freeze_message: __("Syncing from Stripe..."),
						callback(r) {
							if (r.message) {
								frappe.msgprint({
									title: __("Sync Complete"),
									message: __(
										"Matched: {0} | Unmatched: {1}",
										[r.message.matched, r.message.unmatched]
									),
									indicator: "green",
								});
								frm.reload_doc();
							}
						},
					});
				}
			);
		}, __("Actions"));
	},
});
