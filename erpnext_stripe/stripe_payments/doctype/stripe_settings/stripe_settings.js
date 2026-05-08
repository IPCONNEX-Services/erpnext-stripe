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

		frm.add_custom_button(__("Sync Payouts Now"), () => {
			frappe.confirm(
				__("Pull all unimported Stripe payouts since last sync and enqueue per-payout JE creation. Continue?"),
				() => {
					frm.call("sync_payouts_now").then((r) => {
						if (r.message && typeof r.message.enqueued === "number") {
							frappe.show_alert({
								message: __("Enqueued {0} payout(s) (scanned {1}).",
									[r.message.enqueued, r.message.scanned]),
								indicator: "green",
							}, 7);
						}
					});
				}
			);
		}, __("Actions"));
	},
});
