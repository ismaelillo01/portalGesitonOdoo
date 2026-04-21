# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorFaltaJustificada(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Faltas Justificadas',
            'code': 'ZONA_FALTAS_JUSTIFICADAS',
        })

    @classmethod
    def _create_user(cls, suffix):
        return cls.env['usuarios.usuario'].create({
            'name': f'Usuario {suffix}',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
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

    @classmethod
    def _create_absence(cls, trabajador, fecha, hora_inicio, hora_fin, motivo='Cita medica', state='draft'):
        absence = cls.env['trabajadores.falta.justificada'].create({
            'trabajador_id': trabajador.id,
            'fecha': fecha,
            'hora_inicio': hora_inicio,
            'hora_fin': hora_fin,
            'motivo': motivo,
        })
        if state == 'verified':
            absence.action_verificar()
        return absence

    def test_worker_form_exposes_justified_absence_action(self):
        form_arch = self.env.ref('trabajadores.trabajador_form').arch_db
        inherited_arch = self.env.ref(
            'trabajadores.trabajadores_trabajador_form_faltas_justificadas'
        ).arch_db

        self.assertIn('Vacaciones', form_arch)
        self.assertIn('action_open_faltas_justificadas', inherited_arch)
        self.assertIn('Faltas justificadas', inherited_arch)

    def test_justified_absence_draft_does_not_affect_assignment(self):
        usuario = self._create_user('Draft')
        trabajador = self._create_worker('Draft')
        fecha = fields.Date.to_date('2099-04-10')
        asignacion = self._create_assignment(usuario, fecha, [(8.0, 12.0, trabajador)])

        self._create_absence(trabajador, fecha, 9.0, 10.0, state='draft')

        linea = asignacion.lineas_ids
        self.assertFalse(linea.tiene_falta_justificada)
        self.assertEqual(linea.minutos_falta_justificada, 0)
        self.assertEqual(linea.minutos_computables, 240)
        self.assertEqual(asignacion.calendar_bucket_type, 'completed')

    def test_justified_absence_verified_partial_overlap_marks_line_and_bucket(self):
        usuario = self._create_user('Partial')
        trabajador = self._create_worker('Partial')
        fecha = fields.Date.to_date('2099-04-11')
        asignacion = self._create_assignment(usuario, fecha, [(8.0, 12.0, trabajador)], confirmed=True)

        self._create_absence(trabajador, fecha, 9.0, 10.0, motivo='Revision medica', state='verified')

        asignacion.invalidate_recordset(['calendar_bucket_type', 'color_calendario', 'calendar_popover_html'])
        linea = asignacion.lineas_ids
        linea.invalidate_recordset([
            'tiene_falta_justificada',
            'minutos_falta_justificada',
            'minutos_computables',
            'motivo_falta_justificada',
            'incidencia_falta_justificada',
        ])
        self.assertTrue(linea.tiene_falta_justificada)
        self.assertEqual(linea.minutos_falta_justificada, 60)
        self.assertEqual(linea.minutos_computables, 180)
        self.assertEqual(linea.incidencia_falta_justificada, 'Falta justificada parcial')
        self.assertEqual(asignacion.calendar_bucket_type, 'justified')
        self.assertEqual(asignacion.color_calendario, 4)
        self.assertIn('Revision medica', asignacion.calendar_popover_html)

    def test_justified_absence_without_overlap_keeps_assignment_completed(self):
        usuario = self._create_user('No Overlap')
        trabajador = self._create_worker('No Overlap')
        fecha = fields.Date.to_date('2099-04-12')
        asignacion = self._create_assignment(usuario, fecha, [(8.0, 10.0, trabajador)])

        self._create_absence(trabajador, fecha, 12.0, 13.0, state='verified')

        linea = asignacion.lineas_ids
        self.assertFalse(linea.tiene_falta_justificada)
        self.assertEqual(linea.minutos_computables, 120)
        self.assertEqual(asignacion.calendar_bucket_type, 'completed')

    def test_justified_absence_revert_to_draft_clears_effect(self):
        usuario = self._create_user('Revert')
        trabajador = self._create_worker('Revert')
        fecha = fields.Date.to_date('2099-04-13')
        asignacion = self._create_assignment(usuario, fecha, [(8.0, 11.0, trabajador)])
        absence = self._create_absence(trabajador, fecha, 9.0, 10.0, state='verified')

        absence.action_borrador()

        linea = asignacion.lineas_ids
        linea.invalidate_recordset([
            'tiene_falta_justificada',
            'minutos_falta_justificada',
            'minutos_computables',
            'incidencia_falta_justificada',
        ])
        asignacion.invalidate_recordset(['calendar_bucket_type'])
        self.assertFalse(linea.tiene_falta_justificada)
        self.assertEqual(linea.minutos_falta_justificada, 0)
        self.assertEqual(linea.minutos_computables, 180)
        self.assertFalse(linea.incidencia_falta_justificada)
        self.assertEqual(asignacion.calendar_bucket_type, 'completed')

    def test_justified_absence_applies_when_schedule_is_created_after_verification(self):
        usuario = self._create_user('Later Schedule')
        trabajador = self._create_worker('Later Schedule')
        fecha = fields.Date.to_date('2099-04-14')

        self._create_absence(trabajador, fecha, 8.5, 9.5, motivo='Consulta', state='verified')
        asignacion = self._create_assignment(usuario, fecha, [(8.0, 10.0, trabajador)])

        linea = asignacion.lineas_ids
        self.assertTrue(linea.tiene_falta_justificada)
        self.assertEqual(linea.minutos_falta_justificada, 60)
        self.assertEqual(linea.minutos_computables, 60)
        self.assertEqual(asignacion.calendar_bucket_type, 'justified')

    def test_justified_absence_rejects_overlapping_ranges_for_same_worker(self):
        trabajador = self._create_worker('Overlap Constraint')
        fecha = fields.Date.to_date('2099-04-15')

        self._create_absence(trabajador, fecha, 9.0, 11.0)
        with self.assertRaises(ValidationError):
            self._create_absence(trabajador, fecha, 10.0, 12.0)

    def test_calendar_bucket_summary_orders_missing_pending_justified_completed(self):
        fecha = fields.Date.to_date('2099-04-16')
        trabajador_missing = self._create_worker('Bucket Missing')
        trabajador_justified = self._create_worker('Bucket Justified')
        trabajador_completed = self._create_worker('Bucket Completed')

        asignacion_missing = self._create_assignment(
            self._create_user('Bucket Missing'),
            fecha,
            [(8.0, 10.0, trabajador_missing), (10.0, 12.0, None)],
            confirmed=True,
        )
        asignacion_pending = self._create_assignment(
            self._create_user('Bucket Pending'),
            fecha,
            [(8.0, 10.0, None)],
            confirmed=True,
        )
        asignacion_justified = self._create_assignment(
            self._create_user('Bucket Justified'),
            fecha,
            [(8.0, 10.0, trabajador_justified)],
            confirmed=True,
        )
        asignacion_completed = self._create_assignment(
            self._create_user('Bucket Completed'),
            fecha,
            [(8.0, 10.0, trabajador_completed)],
            confirmed=True,
        )
        self._create_absence(trabajador_justified, fecha, 8.0, 9.0, state='verified')

        buckets = self.env['portalgestor.asignacion'].get_calendar_bucket_summary(
            fields.Date.to_string(fecha),
            fields.Date.to_string(fecha),
        )

        self.assertEqual(
            [(bucket['bucket_type'], bucket['title']) for bucket in buckets],
            [
                ('missing', 'Faltantes [1]'),
                ('pending', 'Por asignar [1]'),
                ('justified', 'Falta justificada [1]'),
                ('completed', 'Completados [1]'),
            ],
        )
        self.assertEqual(asignacion_missing.calendar_bucket_type, 'missing')
        self.assertEqual(asignacion_pending.calendar_bucket_type, 'pending')
        self.assertEqual(asignacion_justified.calendar_bucket_type, 'justified')
        self.assertEqual(asignacion_completed.calendar_bucket_type, 'completed')

    def test_ap_report_payload_uses_computable_hours(self):
        usuario = self._create_user('AP Report')
        trabajador = self._create_worker('AP Report')
        fecha = fields.Date.to_date('2026-04-17')
        self._create_assignment(usuario, fecha, [(8.0, 11.0, trabajador)], confirmed=True)
        self._create_absence(trabajador, fecha, 9.0, 10.0, motivo='Analitica', state='verified')

        wizard = self.env['portalgestor.report.wizard'].create({
            'trabajador_ids': [(6, 0, [trabajador.id])],
            'mes': '4',
            'anio': '2026',
        })
        payload = wizard._get_report_payload_for_worker(trabajador)

        self.assertEqual(payload['total_duration_label'], '2 Horas y 00 minutos')
        self.assertEqual(payload['total_festive_label'], '0 Horas y 00 minutos')
        self.assertEqual(payload['lines'][0]['incidencia_label'], 'Falta justificada parcial')
        self.assertEqual(payload['lines'][0]['motivo'], 'Analitica')
        self.assertEqual(payload['lines'][0]['horas_no_trabajadas_label'], '1 Horas y 00 minutos')
        self.assertEqual(payload['lines'][0]['horas_computables_label'], '2 Horas y 00 minutos')
        self.assertFalse(payload['lines'][0]['festive_label'])

    def test_usuario_report_payload_and_csv_include_justified_hours(self):
        usuario = self._create_user('User Report')
        trabajador = self._create_worker('User Report')
        fecha = fields.Date.to_date('2026-04-18')
        self._create_assignment(usuario, fecha, [(8.0, 10.0, trabajador)])
        self._create_absence(trabajador, fecha, 8.0, 10.0, motivo='Operacion familiar', state='verified')

        wizard = self.env['portalgestor.usuario.report.wizard'].create({
            'usuario_ids': [(6, 0, [usuario.id])],
            'mes': '4',
            'anio': '2026',
            'formato_salida': 'csv',
        })
        payload = wizard._get_report_payload_for_user(usuario)
        csv_text = wizard._build_csv_bytes_for_user(usuario).decode('utf-8')

        self.assertEqual(payload['total_duration_label'], '0 Horas y 00 minutos')
        self.assertEqual(payload['total_festive_label'], '0 Horas y 00 minutos')
        self.assertEqual(payload['lines'][0]['incidencia_label'], 'No trabajado - Falta justificada')
        self.assertNotIn('motivo', payload['lines'][0])
        self.assertEqual(payload['lines'][0]['justified_label'], '2 Horas y 00 minutos')
        self.assertEqual(payload['lines'][0]['computable_label'], '0 Horas y 00 minutos')
        self.assertIn('Festivo;Detalle festivo;Horas festivas;Incidencia;Horas no trabajadas;Horas computables', csv_text)
        self.assertNotIn('Operacion familiar', csv_text)
