# -*- coding: utf-8 -*-
# Elimina la columna dni_nie antes de que el ORM cree codigo_autenticacion.


def migrate(cr, version):
    cr.execute("ALTER TABLE usuarios_usuario DROP COLUMN IF EXISTS dni_nie")
