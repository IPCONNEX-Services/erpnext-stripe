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
			<button class="btn btn-xs btn-default stripe-setup-add-card">
				${__("Add Card")}
			</button>
			<button class="btn btn-xs btn-default stripe-setup-email-link">
				${__("Email Setup Link")}
			</button>
			<p class="text-muted small mt-2">
				${__("Either one creates the Stripe customer first — nothing exists on Stripe for this account yet.")}
			</p>
		</div>`,
		__("Stripe")
	);
	frm.dashboard.add_indicator(__("No Stripe Customer"), "grey");

	// Same two entry points as the toolbar, right where the empty state is —
	// this is the only place a Customer with no Stripe record can start from.
	_bind(frm, ".stripe-setup-add-card", () => _setup_then_add_card(frm));
	_bind(frm, ".stripe-setup-email-link", () => _setup_then_email_link(frm));

	frm.add_custom_button(__("Add Card"), () => _setup_then_add_card(frm), __("Stripe"));
	frm.add_custom_button(__("Email Setup Link"), () => _setup_then_email_link(frm), __("Stripe"));
}

function _bind(frm, selector, handler) {
	const ns = "click.stripe_setup";
	$(frm.dashboard.wrapper)
		.off(ns, selector)
		.on(ns, selector, (e) => {
			e.preventDefault();
			handler();
		});
}

function _setup_then_add_card(frm) {
	erpnext_stripe.with_stripe_customer(frm.doc.name, (stripe_customer) => {
		erpnext_stripe.add_card(stripe_customer, () => frm.refresh());
	});
}

function _setup_then_email_link(frm) {
	erpnext_stripe.with_stripe_customer(frm.doc.name, (stripe_customer, result) => {
		erpnext_stripe.email_setup_link(frm.doc.name, result.stripe_settings);
		frm.refresh();
	});
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

	frm.add_custom_button(__("Add Card"), () => {
		_with_record_selection(records, (rec) => {
			erpnext_stripe.add_card(rec.name, () => frm.refresh());
		});
	}, __("Stripe"));

	frm.add_custom_button(__("Email Setup Link"), () => {
		_with_settings_selection(records, (stripe_settings) => {
			erpnext_stripe.email_setup_link(frm.doc.name, stripe_settings);
		});
	}, __("Stripe"));

	frm.add_custom_button(__("Copy Setup Link"), () => {
		_with_record_selection(records, (rec) => erpnext_stripe.copy_setup_link(rec.name));
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

function _with_record_selection(records, callback) {
	if (records.length === 1) {
		callback(records[0]);
		return;
	}
	const label = (r) => `${r.stripe_settings} (${r.stripe_customer_id})`;
	frappe.prompt(
		[{
			fieldname: "choice",
			fieldtype: "Select",
			label: __("Stripe Account"),
			options: records.map(label).join("\n"),
			reqd: 1,
		}],
		(v) => callback(records.find((r) => label(r) === v.choice)),
		__("Select Stripe Account")
	);
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
