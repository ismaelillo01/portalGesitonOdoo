# -*- coding: utf-8 -*-
import base64
import io
import zipfile

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorHogarRiesgoReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Hogar Riesgo',
            'code': 'ZONA_HOGAR_RIESGO',
        })
        cls.localidad = cls.env['zonastrabajo.localidad'].create({
            'name': 'Localidad Hogar Riesgo',
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Hogar Riesgo',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

    @classmethod
    def _create_user(cls, name, hogar_riesgo, grupo='agusto'):
        return cls.env['usuarios.usuario'].create({
            'name': name,
            'grupo': grupo,
            'hogar_riesgo': hogar_riesgo,
            'zona_trabajo_id': cls.zone.id,
            'localidad_id': cls.localidad.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })

    @classmethod
    def _create_assignment(cls, usuario, fecha, hora_inicio, hora_fin):
        assignment = cls.env['portalgestor.asignacion'].create({
            'usuario_id': usuario.id,
            'fecha': fecha,
            'lineas_ids': [(0, 0, {
                'hora_inicio': hora_inicio,
                'hora_fin': hora_fin,
                'trabajador_id': cls.worker.id,
            })],
        })
        assignment.write({'confirmado': True})
        return assignment

    def test_hogar_riesgo_report_payload_counts_users_and_hours(self):
        usuario_hr1_a = self._create_user('Usuario HR1 A', 'hr1')
        self._create_user('Usuario HR1 B', 'hr1')
        self._create_user('Usuario HR2', 'hr2')
        fecha = fields.Date.to_date('2026-05-14')
        self._create_assignment(usuario_hr1_a, fecha, 8.0, 11.5)

        wizard = self.env['portalgestor.hogar.riesgo.report.wizard'].create({
            'mes': '5',
            'anio': '2026',
        })
        payload = wizard._get_report_payload_for_hogar_riesgo('hr1')

        self.assertEqual(payload['hogar_label'], 'HR1')
        self.assertEqual(payload['group_label'], 'Agusto')
        self.assertEqual(payload['user_count'], 2)
        self.assertEqual(payload['total_hours_label'], '3 Horas y 30 minutos')
        self.assertEqual(len(payload['user_rows']), 2)
        self.assertEqual(payload['user_rows'][0]['hours_label'], '3 Horas y 30 minutos')
        self.assertEqual(payload['user_rows'][1]['hours_label'], '0 Horas y 00 minutos')

    def test_hogar_riesgo_report_generates_zip_for_all_allowed_groups(self):
        self._create_user('Usuario HR1 ZIP', 'hr1')
        self._create_user('Usuario HR2 ZIP', 'hr2')
        self._create_user('Usuario HR3 ZIP', 'hr3')
        self._create_user('Usuario HR4 ZIP', 'hr4')
        self._create_user('Usuario HS ZIP', 'hs', grupo='intecum')
        self._create_user('Usuario HRB ZIP', 'hrb', grupo='intecum')
        self._create_user('Usuario HRI ZIP', 'hri', grupo='intecum')

        wizard = self.env['portalgestor.hogar.riesgo.report.wizard'].create({
            'mes': '5',
            'anio': '2026',
        })
        action = wizard.action_generate_report()

        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertTrue(wizard.download_file)
        self.assertEqual(wizard.download_filename, 'Hogares de Riesgo (Mayo 2026).zip')

        zip_buffer = io.BytesIO(base64.b64decode(wizard.download_file))
        with zipfile.ZipFile(zip_buffer) as zip_file:
            names = sorted(zip_file.namelist())

        self.assertEqual(len(names), 7)
        self.assertEqual(names, [
            'HR1 (Mayo 2026).pdf',
            'HR2 (Mayo 2026).pdf',
            'HR3 (Mayo 2026).pdf',
            'HR4 (Mayo 2026).pdf',
            'HRB (Mayo 2026).pdf',
            'HRI (Mayo 2026).pdf',
            'HS (Mayo 2026).pdf',
        ])
