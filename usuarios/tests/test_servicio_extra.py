# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestUsuarioServicioExtra(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.taxi_service = cls.env.ref('usuarios.usuarios_servicio_taxi')
        cls.lavanderia_service = cls.env.ref('usuarios.usuarios_servicio_lavanderia')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Servicios Extra',
            'code': 'ZONA_SERVICIOS_EXTRA',
        })

    def _create_user(self):
        return self.env['usuarios.usuario'].create({
            'name': 'Usuario Servicios Extra',
            'grupo': 'agusto',
            'zona_trabajo_id': self.zone.id,
            'servicio_ids': [(6, 0, [self.taxi_service.id, self.lavanderia_service.id])],
        })

    def test_extra_services_report_groups_quantity_and_cost(self):
        usuario = self._create_user()
        Registro = self.env['usuarios.servicio.registro']
        Registro.create({
            'usuario_id': usuario.id,
            'service_code': 'taxi',
            'fecha': date(2026, 5, 1),
            'cantidad': 2,
            'coste': 15.5,
        })
        Registro.create({
            'usuario_id': usuario.id,
            'service_code': 'taxi',
            'fecha': date(2026, 5, 3),
            'cantidad': 1,
            'coste': 7.25,
        })
        Registro.create({
            'usuario_id': usuario.id,
            'service_code': 'lavanderia',
            'fecha': date(2026, 5, 4),
            'cantidad': 3,
            'coste': 12.0,
        })
        Registro.create({
            'usuario_id': usuario.id,
            'service_code': 'taxi',
            'fecha': date(2026, 6, 1),
            'cantidad': 1,
            'coste': 99.0,
        })

        data = usuario._get_extra_services_report_data(date(2026, 5, 1), date(2026, 5, 31))
        summary_by_service = {
            line['service_label']: line
            for line in data['summary_lines']
        }

        self.assertEqual(len(data['lines']), 3)
        self.assertEqual(summary_by_service['Taxi']['total_quantity'], 2)
        self.assertAlmostEqual(summary_by_service['Taxi']['total_cost'], 22.75)
        self.assertEqual(summary_by_service['Lavanderia']['total_quantity'], 3)
        self.assertAlmostEqual(summary_by_service['Lavanderia']['total_cost'], 36.0)
        self.assertEqual(data['lines'][0]['quantity_display'], '')
        self.assertEqual(data['lines'][2]['quantity_display'], '3 Usos')

    def test_extra_service_quantity_and_cost_validation(self):
        usuario = self._create_user()

        with self.assertRaises(ValidationError):
            self.env['usuarios.servicio.registro'].create({
                'usuario_id': usuario.id,
                'service_code': 'lavanderia',
                'fecha': date(2026, 5, 1),
                'cantidad': 0,
                'coste': 1.0,
            })

        with self.assertRaises(ValidationError):
            self.env['usuarios.servicio.registro'].create({
                'usuario_id': usuario.id,
                'service_code': 'lavanderia',
                'fecha': date(2026, 5, 1),
                'cantidad': 1,
                'coste': -1.0,
            })
