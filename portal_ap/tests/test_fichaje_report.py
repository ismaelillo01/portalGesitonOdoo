# -*- coding: utf-8 -*-
from datetime import date, datetime

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalAPFichajeReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Reporte Fichajes',
            'code': 'ZONA_REPORTE_FICHAJES',
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Reporte',
            'apellido1': 'Excel',
            'dni_nie': '12345678Z',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Reporte',
            'apellido1': 'Uno',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.assignment_day_1 = cls.env['portalgestor.asignacion'].create({
            'usuario_id': cls.usuario.id,
            'fecha': date(2026, 5, 19),
            'confirmado': True,
        })
        cls.assignment_day_2 = cls.env['portalgestor.asignacion'].create({
            'usuario_id': cls.usuario.id,
            'fecha': date(2026, 5, 20),
            'confirmado': True,
        })
        cls.line_1 = cls._create_line(cls.assignment_day_1, 8.0, 10.0)
        cls.line_2 = cls._create_line(cls.assignment_day_1, 11.0, 12.5)
        cls.incomplete_line = cls._create_line(cls.assignment_day_2, 8.0, 9.0)
        cls.line_3 = cls._create_line(cls.assignment_day_2, 10.0, 11.0)
        cls._create_check(cls.line_1, 'in', datetime(2026, 5, 19, 8, 0), 'event-report-1-in')
        cls._create_check(cls.line_1, 'out', datetime(2026, 5, 19, 10, 0), 'event-report-1-out')
        cls._create_check(cls.line_2, 'in', datetime(2026, 5, 19, 11, 0), 'event-report-2-in-a')
        cls._create_check(cls.line_2, 'in', datetime(2026, 5, 19, 11, 5), 'event-report-2-in-b')
        cls._create_check(cls.line_2, 'out', datetime(2026, 5, 19, 12, 30), 'event-report-2-out')
        cls._create_check(cls.incomplete_line, 'in', datetime(2026, 5, 20, 8, 0), 'event-report-3-in')
        cls._create_check(cls.incomplete_line, 'out', datetime(2026, 5, 20, 9, 0), 'event-report-rejected-out', state='rejected')
        cls._create_check(
            cls.line_3,
            'in',
            datetime(2026, 5, 20, 15, 0),
            'event-report-4-in',
            origin='offline',
            client_datetime='2026-05-20T10:00:00+02:00',
        )
        cls._create_check(
            cls.line_3,
            'out',
            datetime(2026, 5, 20, 16, 0),
            'event-report-4-out',
            origin='offline',
            client_datetime='2026-05-20T11:00:00+02:00',
        )

    @classmethod
    def _create_line(cls, assignment, start, end):
        return cls.env['portalgestor.asignacion.linea'].create({
            'asignacion_id': assignment.id,
            'hora_inicio': start,
            'hora_fin': end,
            'trabajador_id': cls.worker.id,
        })

    @classmethod
    def _create_check(
        cls,
        line,
        event_type,
        server_datetime,
        client_event_id,
        state='valid',
        origin='online',
        client_datetime='',
    ):
        return cls.env['portal.ap.fichaje'].create({
            'trabajador_id': cls.worker.id,
            'usuario_id': cls.usuario.id,
            'assignment_line_id': line.id,
            'event_type': event_type,
            'server_datetime': fields.Datetime.to_string(server_datetime),
            'client_datetime': client_datetime,
            'client_event_id': client_event_id,
            'origin': origin,
            'state': state,
        })

    def _create_wizard(self):
        return self.env['portal.ap.fichaje.report.wizard'].create({
            'trabajador_id': self.worker.id,
            'mes': '5',
            'anio': '2026',
        })

    def test_report_uses_first_in_last_out_and_ignores_rejected(self):
        data = self._create_wizard()._get_report_data()

        self.assertEqual(data['daily_totals'][date(2026, 5, 19)], 210)
        self.assertEqual(data['daily_totals'][date(2026, 5, 20)], 60)
        self.assertEqual(data['total_minutes'], 270)

        duplicate_row = next(row for row in data['rows'] if row['minutes'] == 90)
        self.assertIn('Varias entradas', duplicate_row['incidence'])
        incomplete_row = next(row for row in data['rows'] if row['check_out'] is False)
        self.assertEqual(incomplete_row['minutes'], 0)
        self.assertIn('Sin salida', incomplete_row['incidence'])
        offline_row = next(
            row
            for row in data['rows']
            if row['date'] == date(2026, 5, 20) and row['minutes'] == 60
        )
        self.assertEqual(offline_row['check_in'], datetime(2026, 5, 20, 10, 0))
        self.assertEqual(offline_row['check_out'], datetime(2026, 5, 20, 11, 0))

    def test_xlsx_generation_returns_excel_file(self):
        content = self._create_wizard()._generate_xlsx_content()

        self.assertTrue(content.startswith(b'PK'))
