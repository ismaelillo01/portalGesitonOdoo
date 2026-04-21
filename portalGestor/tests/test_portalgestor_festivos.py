# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorFestivos(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Festivos Portal',
            'code': 'ZONA_FESTIVOS_PORTAL',
        })
        cls.localidad_a = cls.env['zonastrabajo.localidad'].create({
            'name': 'Localidad Portal Festivos A',
        })
        cls.localidad_b = cls.env['zonastrabajo.localidad'].create({
            'name': 'Localidad Portal Festivos B',
        })

    @classmethod
    def _create_user(cls, suffix, localidad=None):
        return cls.env['usuarios.usuario'].create({
            'name': f'Usuario {suffix}',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'localidad_id': localidad.id if localidad else False,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })

    @classmethod
    def _create_worker(cls, suffix):
        return cls.env['trabajadores.trabajador'].create({
            'name': f'AP {suffix}',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

    @classmethod
    def _create_assignment(cls, usuario, fecha, line_specs, confirmed=False):
        assignment = cls.env['portalgestor.asignacion'].create({
            'usuario_id': usuario.id,
            'fecha': fecha,
            'lineas_ids': [
                (
                    0,
                    0,
                    {
                        'hora_inicio': hora_inicio,
                        'hora_fin': hora_fin,
                        'trabajador_id': trabajador.id if trabajador else False,
                    },
                )
                for hora_inicio, hora_fin, trabajador in line_specs
            ],
        })
        if confirmed:
            assignment.write({'confirmado': True})
        return assignment

    def test_calendar_holiday_markers_show_local_only_with_worker_filter(self):
        worker = self._create_worker('Markers')
        holiday_date = fields.Date.to_date('2026-04-19')
        self.env['trabajadores.festivo.oficial'].create({
            'name': 'Fiesta de Castilla y Leon',
            'fecha': holiday_date,
            'source_scope': 'autonomic',
        })
        self.env['trabajadores.festivo.local'].create({
            'trabajador_id': worker.id,
            'fecha': holiday_date,
            'localidad_id': self.localidad_a.id,
            'name': 'Fiesta propia AP',
        })

        marker_without_worker = self.env['portalgestor.asignacion'].get_calendar_holiday_markers(
            fields.Date.to_string(holiday_date),
            fields.Date.to_string(holiday_date),
        )[0]
        marker_with_worker = self.env['portalgestor.asignacion'].get_calendar_holiday_markers(
            fields.Date.to_string(holiday_date),
            fields.Date.to_string(holiday_date),
            worker.id,
        )[0]

        self.assertEqual(marker_without_worker['marker_type'], 'official')
        self.assertEqual(marker_with_worker['marker_type'], 'combined')
        self.assertIn('Fiesta propia AP', marker_with_worker['names'])
        self.assertIn(self.localidad_a.name, marker_with_worker['names'])

    def test_portalgestor_reports_include_festive_hours(self):
        usuario = self._create_user('Festivo', localidad=self.localidad_a)
        worker = self._create_worker('Festivo')
        holiday_date = fields.Date.to_date('2026-04-20')
        self.env['trabajadores.festivo.oficial'].create({
            'name': 'Fiesta de Castilla y Leon',
            'fecha': holiday_date,
            'source_scope': 'autonomic',
        })
        self.env['trabajadores.festivo.local'].create({
            'trabajador_id': worker.id,
            'fecha': holiday_date,
            'localidad_id': self.localidad_a.id,
            'name': 'Festivo AP',
        })
        assignment = self._create_assignment(usuario, holiday_date, [(8.0, 11.0, worker)], confirmed=True)
        self.env['trabajadores.falta.justificada'].create({
            'trabajador_id': worker.id,
            'fecha': holiday_date,
            'hora_inicio': 9.0,
            'hora_fin': 10.0,
            'motivo': 'Consulta',
            'state': 'verified',
        })
        assignment.lineas_ids._recompute_falta_justificada_metrics()
        assignment.lineas_ids.write({
            'festivo_oficial_id': False,
            'festivo_local_id': False,
            'tiene_festivo': False,
            'minutos_festivos': 0,
            'etiqueta_festivo': False,
            'nombres_festivo': False,
        })

        worker_wizard = self.env['portalgestor.report.wizard'].create({
            'trabajador_ids': [(6, 0, [worker.id])],
            'mes': '4',
            'anio': '2026',
        })
        worker_payload = worker_wizard._get_report_payload_for_worker(worker)
        user_wizard = self.env['portalgestor.usuario.report.wizard'].create({
            'usuario_ids': [(6, 0, [usuario.id])],
            'mes': '4',
            'anio': '2026',
            'formato_salida': 'csv',
        })
        user_payload = user_wizard._get_report_payload_for_user(usuario)
        csv_text = user_wizard._build_csv_bytes_for_user(usuario).decode('utf-8')

        self.assertEqual(worker_payload['lines'][0]['festive_label'], 'Festivo oficial + local AP')
        self.assertEqual(worker_payload['lines'][0]['horas_festivas_label'], '2 Horas y 00 minutos')
        self.assertEqual(worker_payload['total_festive_label'], '2 Horas y 00 minutos')
        self.assertEqual(user_payload['lines'][0]['festive_label'], 'Festivo oficial + local AP')
        self.assertEqual(user_payload['lines'][0]['festive_hours_label'], '2 Horas y 00 minutos')
        self.assertEqual(user_payload['total_festive_label'], '2 Horas y 00 minutos')
        self.assertIn('Festivo;Detalle festivo;Horas festivas', csv_text)
        self.assertIn('Festivo oficial + local AP', csv_text)
        self.assertIn(self.localidad_a.name, csv_text)

    def test_local_holiday_only_applies_when_user_locality_matches(self):
        usuario_festivo = self._create_user('Palencia', localidad=self.localidad_a)
        usuario_normal = self._create_user('Villamuriel', localidad=self.localidad_b)
        worker = self._create_worker('Localidad')
        holiday_date = fields.Date.to_date('2026-04-24')
        self.env['trabajadores.festivo.local'].create({
            'trabajador_id': worker.id,
            'fecha': holiday_date,
            'localidad_id': self.localidad_a.id,
            'name': 'Fiesta local AP',
        })

        self._create_assignment(usuario_festivo, holiday_date, [(15.0, 16.0, worker)], confirmed=True)
        self._create_assignment(usuario_normal, holiday_date, [(17.0, 19.0, worker)], confirmed=True)

        worker_wizard = self.env['portalgestor.report.wizard'].create({
            'trabajador_ids': [(6, 0, [worker.id])],
            'mes': '4',
            'anio': '2026',
        })
        worker_payload = worker_wizard._get_report_payload_for_worker(worker)

        self.assertEqual(len(worker_payload['lines']), 2)
        self.assertEqual(worker_payload['lines'][0]['usuario_name'], usuario_festivo.display_name or usuario_festivo.name)
        self.assertEqual(worker_payload['lines'][0]['festive_label'], 'Festivo local AP')
        self.assertEqual(worker_payload['lines'][0]['horas_festivas_label'], '1 Horas y 00 minutos')
        self.assertIn(self.localidad_a.name, worker_payload['lines'][0]['festive_names'])
        self.assertEqual(worker_payload['lines'][1]['usuario_name'], usuario_normal.display_name or usuario_normal.name)
        self.assertEqual(worker_payload['lines'][1]['festive_label'], '')
        self.assertEqual(worker_payload['lines'][1]['horas_festivas_label'], '0 Horas y 00 minutos')
        self.assertEqual(worker_payload['total_festive_label'], '1 Horas y 00 minutos')
