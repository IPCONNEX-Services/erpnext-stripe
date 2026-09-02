// The card-setup actions themselves live in public/js/stripe_card_dialog.js so
// the Customer form can offer the same three before a Stripe Customer exists.
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

		const group = __("Add Card");

		// Agent types the card here, in the desk.
		frm.add_custom_button(__("Add Card"), () => {
			erpnext_stripe.add_card(frm.doc.name, () => frm.reload_doc());
		}, group);

		// Customer types it themselves, from a link that expires.
		frm.add_custom_button(__("Email Setup Link to Customer"), () => {
			erpnext_stripe.email_setup_link(frm.doc.customer, frm.doc.stripe_settings);
		}, group);

		frm.add_custom_button(__("Copy Setup Link"), () => {
			erpnext_stripe.copy_setup_link(frm.doc.name);
		}, group);
	},
});
