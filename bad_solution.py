from decimal import Decimal

import orbital


def process_arrived_cargos(track_ids):
    all_cargos = orbital.cargos(track_ids)
    grouped = {}
    for cargo in all_cargos:
        key = orbital.format_status(cargo.status)
        grouped.setdefault(key, []).append(cargo)

    result = []
    for cargo in grouped.get("ARRIVED", []):
        first_multiplier = orbital.insurance_multiplier(cargo.id)
        if first_multiplier > Decimal("1"):
            insured_value = cargo.declared_value * orbital.insurance_multiplier(cargo.id)
        else:
            insured_value = cargo.declared_value

        cl = orbital.client(cargo.client_id)
        cargo.final_value = insured_value - cargo.declared_value * (cl.rebate_percent / Decimal("100"))
        cargo.status = orbital.parse_status("INVOICED")
        orbital.mark_dirty(cargo)
        orbital.save_dirty()
        result.append(cargo)
    return result
