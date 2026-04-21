# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestUsuarioHogarRiesgo(TransactionCase):

    def setUp(self):
        super().setUp()
        self.usuario_model = self.env['usuarios.usuario']
        self.zona = self.env['zonastrabajo.zona'].create({
            'name': 'Zona Test Hogar Riesgo',
            'code': 'ZTHR',
        })

    def _usuario_vals(self, **overrides):
        vals = {
            'name': 'Usuario Test',
            'grupo': 'agusto',
            'zona_trabajo_id': self.zona.id,
        }
        vals.update(overrides)
        return vals

    def test_agusto_accepts_hr_values(self):
        usuario = self.usuario_model.create(self._usuario_vals(hogar_riesgo='hr3'))
        self.assertEqual(usuario.hogar_riesgo, 'hr3')

    def test_intecum_accepts_hs_hrb_hri(self):
        usuario = self.usuario_model.create(self._usuario_vals(grupo='intecum', hogar_riesgo='hs'))
        self.assertEqual(usuario.hogar_riesgo, 'hs')

    def test_agusto_rejects_intecum_values(self):
        with self.assertRaises(ValidationError):
            self.usuario_model.create(self._usuario_vals(hogar_riesgo='hs'))

    def test_intecum_rejects_agusto_values(self):
        usuario = self.usuario_model.create(self._usuario_vals(grupo='intecum'))
        with self.assertRaises(ValidationError):
            usuario.write({'hogar_riesgo': 'hr2'})
