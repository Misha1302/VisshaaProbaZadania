from decimal import Decimal

import orbital


def process_arrived_cargos(track_ids):
    arrived = orbital.cargos(track_ids, orbital.CargoStatus.ARRIVED)
    target_status = orbital.CargoStatus.INVOICED
    clients_cache = {}
    result = []

    for cargo in arrived:
        mult = orbital.insurance_multiplier(cargo.id)
        declared = cargo.declared_value
        insured = declared * mult if mult > Decimal("1") else declared

        cl = clients_cache.get(cargo.client_id)
        if cl is None:
            cl = orbital.client(cargo.client_id)
            clients_cache[cargo.client_id] = cl

        cargo.final_value = insured - declared * (cl.rebate_percent / Decimal("100"))
        cargo.status = target_status
        orbital.mark_dirty(cargo)
        result.append(cargo)

    if result:
        orbital.save_dirty()

    return result
