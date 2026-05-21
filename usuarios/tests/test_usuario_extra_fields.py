# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestUsuarioExtraFields(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Campos Usuario',
            'code': 'ZONA_CAMPOS_USUARIO',
        })

    def test_codigo_and_grado_dependencia_are_stored(self):
        for value in ['0', '1', '2', '3', '3_plus']:
            usuario = self.env['usuarios.usuario'].create({
                'name': 'Usuario',
                'apellido1': value,
                'codigo': 'INT-%s' % value,
                'grado_dependencia': value,
                'grupo': 'agusto',
                'zona_trabajo_id': self.zone.id,
            })

            self.assertEqual(usuario.codigo, 'INT-%s' % value)
            self.assertEqual(usuario.grado_dependencia, value)
