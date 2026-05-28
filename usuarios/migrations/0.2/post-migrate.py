# -*- coding: utf-8 -*-
# Genera codigos de autenticacion unicos de 4 digitos para los usuarios existentes.
import random


def migrate(cr, version):
    cr.execute("SELECT id FROM usuarios_usuario WHERE codigo_autenticacion IS NULL")
    records = cr.fetchall()
    if not records:
        return

    cr.execute("SELECT codigo_autenticacion FROM usuarios_usuario WHERE codigo_autenticacion IS NOT NULL")
    existing = {row[0] for row in cr.fetchall()}

    available = [f'{i:04d}' for i in range(10000) if f'{i:04d}' not in existing]
    random.shuffle(available)

    for i, (rec_id,) in enumerate(records):
        cr.execute(
            "UPDATE usuarios_usuario SET codigo_autenticacion = %s WHERE id = %s",
            (available[i], rec_id),
        )
