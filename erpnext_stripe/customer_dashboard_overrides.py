from frappe import _


def add_stripe(data):
	"""Append Stripe Customer to the Customer form's Connections tab.

	Receives the dict from `erpnext.selling.doctype.customer.customer_dashboard.get_data`
	plus any overrides applied by other apps before us (frappe chains every hook in
	`Meta.get_dashboard_data`, so ipconnex_recurring / fonotel_telephony still apply).
	Returns it modified in place.

	Stripe Customer links back through its own `customer` field, so no
	non_standard_fieldnames entry is needed.
	"""
	if not isinstance(data, dict):
		return data

	transactions = data.setdefault("transactions", [])
	transactions.append({"label": _("Stripe"), "items": ["Stripe Customer"]})

	return data
