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
			? `${(defaultPm.brand || "CARD").toUpperCase()} •••• ${defaultPm.last4} (${defaultPm.exp_month}/${defaultPm.exp_year})`
			: `<span class="text-muted">${__("No default card")}</span>`;

		// The Stripe Customer docname IS the cus_ id (autoname: field:stripe_customer_id),
		// so the id itself is the shortest route to the doc where the trigger / cards
		// are configured. get_form_link() keeps us off a hardcoded /desk vs /app prefix.
		const doc_link = frappe.utils.get_form_link("Stripe Customer", rec.name);
		const unmatched = rec.unmatched_flag
			? ` <span class="badge badge-danger">${__("Unmatched")}</span>`
			: "";

		html += `
			<div class="row" style="margin-bottom: 8px;">
				<div class="col-xs-6">
					${badge} <strong>${frappe.utils.escape_html(rec.company || "")}</strong>${unmatched}<br>
					<a href="${doc_link}" class="stripe-customer-link" data-name="${frappe.utils.escape_html(rec.name)}">
						${frappe.utils.escape_html(rec.stripe_customer_id)}
					</a>
				</div>
				<div class="col-xs-6">
					${cardLine}<br>
					<small class="text-muted">${__("Charge trigger")}: ${_trigger_label(rec)}</small>
					&nbsp;<a href="${doc_link}" class="stripe-customer-link" data-name="${frappe.utils.escape_html(rec.name)}">
						<small>${__("Configure")}</small>
					</a>
				</div>
			</div>`;
	}

	html += `</div>`;

	frm.dashboard.add_section(html, __("Stripe"));

	// Namespaced + rebound on every refresh so handlers never stack up.
	$(frm.dashboard.wrapper)
		.off("click.stripe_customer_link")
		.on("click.stripe_customer_link", "a.stripe-customer-link", function (e) {
			e.preventDefault();
			frappe.set_route("Form", "Stripe Customer", $(this).data("name"));
		});

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

function _trigger_label(rec) {
	const override = rec.payment_trigger_override;
	if (!override || override === "Use Company Default") {
		return __("Company default");
	}
	if (override === "After X Days") {
		return __("After {0} day(s)", [rec.payment_trigger_days_override || 0]);
	}
	return __(override);
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
