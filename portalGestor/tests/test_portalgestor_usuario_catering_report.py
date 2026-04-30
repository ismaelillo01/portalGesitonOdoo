# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorUsuarioCateringReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.catering_comida_service = cls.env.ref('usuarios.usuarios_servicio_catering_comida')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Usuario Catering Report',
            'code': 'ZONA_USUARIO_CATERING_REPORT',
        })
        cls.localidad = cls.env['zonastrabajo.localidad'].create({
            'name': 'Localidad Usuario Catering Report',
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Usuario Catering Report',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

    def test_usuario_report_payload_includes_catering_dates(self):
        usuario = self.env['usuarios.usuario'].create({
            'name': 'Usuario Reporte Catering',
            'grupo': 'agusto',
            'zona_trabajo_id': self.zone.id,
            'localidad_id': self.localidad.id,
            'servicio_ids': [(6, 0, [self.ap_service.id, self.catering_comida_service.id])],
        })
        config = self.env['usuarios.catering.config'].create({
            'usuario_id': usuario.id,
            'service_code': 'catering_comida',
            'proovedor': 'Catering Central',
            'date_start': date(2026, 5, 1),
            'date_stop': date(2026, 5, 31),
            'lunes': True,
        })
        self.env['usuarios.catering.suspension'].create({
            'config_id': config.id,
            'date_start': date(2026, 5, 11),
            'date_stop': date(2026, 5, 15),
            'name': 'Vacaciones mayo',
        })

        assignment = self.env['portalgestor.asignacion'].create({
            'usuario_id': usuario.id,
            'fecha': date(2026, 5, 6),
            'lineas_ids': [(0, 0, {
                'hora_inicio': 8.0,
                'hora_fin': 10.0,
                'trabajador_id': self.worker.id,
            })],
        })
        assignment.write({'confirmado': True})

        wizard = self.env['portalgestor.usuario.report.wizard'].create({
            'usuario_ids': [(6, 0, [usuario.id])],
            'mes': '5',
            'anio': '2026',
            'formato_salida': 'pdf',
        })
        payload = wizard._get_report_payload_for_user(usuario)

        self.assertEqual(payload['total_duration_label'], '2 Horas y 00 minutos')
        self.assertEqual(payload['catering_summary_lines'], [
            {'service_label': 'Catering comida', 'provider_label': 'Catering Central', 'count': 3},
        ])
        self.assertEqual(payload['catering_lines'], [
            {
                'fecha_label': '04/05/2026',
                'services_label': 'Catering comida',
                'providers_label': 'Catering Central',
            },
            {
                'fecha_label': '18/05/2026',
                'services_label': 'Catering comida',
                'providers_label': 'Catering Central',
            },
            {
                'fecha_label': '25/05/2026',
                'services_label': 'Catering comida',
                'providers_label': 'Catering Central',
            },
        ])
