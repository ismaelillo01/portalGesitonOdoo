# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalAPMobileService(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env['portal.ap.service'].sudo()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Mobile AP',
            'code': 'ZONA_MOBILE_AP',
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Mobile',
            'apellido1': 'Prueba',
            'dni_nie': '32165498P',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Mobile',
            'apellido1': 'Uno',
            'direccion': 'Calle Mobile 1',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.other_user = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Mobile',
            'apellido1': 'Dos',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.usuario._ensure_portal_ap_qr_token()
        cls.other_user._ensure_portal_ap_qr_token()
        cls.assignment = cls.env['portalgestor.asignacion'].create({
            'usuario_id': cls.usuario.id,
            'fecha': fields.Date.today() + timedelta(days=1),
            'confirmado': True,
        })
        cls.line = cls.env['portalgestor.asignacion.linea'].create({
            'asignacion_id': cls.assignment.id,
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': cls.worker.id,
        })

    def _login(self):
        response = self.service._mobile_login('3216-5498p', device_id='test-device', device_label='Android Test')
        self.assertTrue(response['ok'])
        self.assertTrue(response['session_token'])
        return response['session_token']

    def test_mobile_login_normalizes_dni(self):
        token = self._login()
        session = self.env['portal.ap.mobile.session'].search([('token', '=', token)])
        self.assertEqual(session.trabajador_id, self.worker)
        self.assertEqual(session.device_id, 'test-device')

    def test_mobile_schedule_returns_confirmed_user_qr_scope(self):
        token = self._login()
        month = fields.Date.to_string(self.assignment.fecha)[:7]
        response = self.service._mobile_schedule(token, month)

        self.assertTrue(response['ok'])
        self.assertEqual(len(response['shifts']), 1)
        self.assertEqual(response['shifts'][0]['id'], self.line.id)
        self.assertEqual(response['shifts'][0]['usuario']['id'], self.usuario.id)
        self.assertEqual(response['shifts'][0]['status'], 'pending')

    def test_mobile_check_accepts_qr_for_assignment_user(self):
        token = self._login()
        response = self.service._mobile_check(token, {
            'assignment_line_id': self.line.id,
            'qr_token': self.usuario.portal_ap_qr_token,
            'event_type': 'in',
            'client_event_id': 'event-valid-1',
            'client_datetime': '2026-05-18T10:00:00+02:00',
        })

        self.assertTrue(response['ok'])
        self.assertIn(response['fichaje']['state'], ('valid', 'warning'))
        self.assertEqual(response['fichaje']['event_type'], 'in')

    def test_mobile_check_rejects_qr_from_other_user(self):
        token = self._login()
        response = self.service._mobile_check(token, {
            'assignment_line_id': self.line.id,
            'qr_token': self.other_user.portal_ap_qr_token,
            'event_type': 'in',
            'client_event_id': 'event-rejected-1',
        })

        self.assertFalse(response['ok'])
        self.assertEqual(response['fichaje']['state'], 'rejected')
        self.assertIn('QR', response['error']['message'])

    def test_mobile_sync_is_idempotent_by_client_event_id(self):
        token = self._login()
        event = {
            'assignment_line_id': self.line.id,
            'qr_token': self.usuario.portal_ap_qr_token,
            'event_type': 'out',
            'client_event_id': 'event-offline-1',
            'origin': 'offline',
        }

        first = self.service._mobile_sync(token, [event])
        second = self.service._mobile_sync(token, [event])

        self.assertTrue(first['ok'])
        self.assertTrue(second['ok'])
        checks = self.env['portal.ap.fichaje'].search([('client_event_id', '=', 'event-offline-1')])
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks.origin, 'offline')
