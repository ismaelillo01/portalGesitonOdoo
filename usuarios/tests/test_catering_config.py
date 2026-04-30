# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests.common import TransactionCase


class TestUsuarioCateringConfig(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.catering_comida_service = cls.env.ref('usuarios.usuarios_servicio_catering_comida')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Catering Test',
            'code': 'ZONA_CATERING_TEST',
        })
        cls.localidad = cls.env['zonastrabajo.localidad'].create({
            'name': 'Localidad Catering Test',
        })

    def test_catering_action_and_occurrences_respect_suspensions(self):
        usuario = self.env['usuarios.usuario'].create({
            'name': 'Usuario Catering',
            'grupo': 'agusto',
            'zona_trabajo_id': self.zone.id,
            'localidad_id': self.localidad.id,
            'servicio_ids': [(6, 0, [self.catering_comida_service.id])],
        })

        self.assertTrue(usuario.has_catering_comida_service)
        self.assertFalse(usuario.has_catering_cena_service)

        action = usuario.action_open_catering_comida_config()
        self.assertEqual(action['res_model'], 'usuarios.catering.config')
        self.assertEqual(action['context']['default_usuario_id'], usuario.id)
        self.assertEqual(action['context']['default_service_code'], 'catering_comida')
        self.assertNotIn('res_id', action)

        config = self.env['usuarios.catering.config'].create({
            'usuario_id': usuario.id,
            'service_code': 'catering_comida',
            'date_start': date(2026, 5, 1),
            'date_stop': date(2026, 5, 31),
            'lunes': True,
        })
        self.env['usuarios.catering.suspension'].create({
            'config_id': config.id,
            'date_start': date(2026, 5, 11),
            'date_stop': date(2026, 5, 15),
            'name': 'Vacaciones',
        })

        occurrences = config._get_occurrence_dates(date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(occurrences, [
            date(2026, 5, 4),
            date(2026, 5, 18),
            date(2026, 5, 25),
        ])
