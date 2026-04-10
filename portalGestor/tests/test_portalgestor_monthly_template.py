# -*- coding: utf-8 -*-
import calendar

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorMonthlyTemplate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Plantilla Mensual',
            'code': 'ZONA_PLANTILLA_MENSUAL',
        })
        cls.usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Plantilla Mensual',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.other_user = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Conflicto',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.worker_a = cls.env['trabajadores.trabajador'].create({
            'name': 'AP A',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.worker_b = cls.env['trabajadores.trabajador'].create({
            'name': 'AP B',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

    @classmethod
    def _create_template(cls, month, year):
        return cls.env['portalgestor.asignacion.mensual'].create({
            'schedule_type': 'monthly_template',
            'usuario_id': cls.usuario.id,
            'month': str(month),
            'year': year,
        })

    def test_monthly_template_creates_real_week_structure(self):
        template = self._create_template(4, 2026)
        expected_weeks = len(calendar.Calendar(firstweekday=0).monthdatescalendar(2026, 4))
        self.assertEqual(template.schedule_type, 'monthly_template')
        self.assertEqual(len(template.template_week_ids), expected_weeks)
        self.assertEqual(template.fecha_inicio, fields.Date.to_date('2026-04-01'))
        self.assertEqual(template.fecha_fin, fields.Date.to_date('2026-04-30'))

    def test_selected_days_seed_from_first_day(self):
        template = self._create_template(4, 2026)
        week = template.template_week_ids.sorted('sequence')[1]
        monday = week.template_day_ids.filtered(lambda day: day.weekday_index == 0)[:1]
        tuesday = week.template_day_ids.filtered(lambda day: day.weekday_index == 1)[:1]
        friday = week.template_day_ids.filtered(lambda day: day.weekday_index == 4)[:1]
        (monday | tuesday | friday).write({'selected_for_seed': True})

        self.env['portalgestor.asignacion.mensual.dia.linea'].create({
            'template_day_id': monday.id,
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })

        self.assertEqual(tuesday.template_day_line_ids.mapped('trabajador_id'), self.worker_a)
        self.assertEqual(friday.template_day_line_ids.mapped('trabajador_id'), self.worker_a)
        self.assertEqual(tuesday.seed_source_day_id, monday)
        self.assertTrue(tuesday.seed_is_pristine)

    def test_copy_week_to_next_week_replaces_same_weekdays_only(self):
        template = self._create_template(4, 2026)
        first_week = template.template_week_ids.sorted('sequence')[1]
        second_week = template.template_week_ids.sorted('sequence')[2]
        monday = first_week.template_day_ids.filtered(lambda day: day.weekday_index == 0)[:1]
        friday = first_week.template_day_ids.filtered(lambda day: day.weekday_index == 4)[:1]
        second_monday = second_week.template_day_ids.filtered(lambda day: day.weekday_index == 0)[:1]
        second_wednesday = second_week.template_day_ids.filtered(lambda day: day.weekday_index == 2)[:1]

        self.env['portalgestor.asignacion.mensual.dia.linea'].create([
            {
                'template_day_id': monday.id,
                'hora_inicio': 8.0,
                'hora_fin': 10.0,
                'trabajador_id': self.worker_a.id,
            },
            {
                'template_day_id': friday.id,
                'hora_inicio': 12.0,
                'hora_fin': 14.0,
                'trabajador_id': self.worker_b.id,
            },
            {
                'template_day_id': second_wednesday.id,
                'hora_inicio': 9.0,
                'hora_fin': 11.0,
                'trabajador_id': self.worker_b.id,
            },
        ])

        first_week.action_copy_to_next_week()

        self.assertEqual(second_monday.template_day_line_ids.mapped('trabajador_id'), self.worker_a)
        self.assertEqual(second_monday.template_day_line_ids.mapped('hora_inicio'), [8.0])
        self.assertEqual(second_wednesday.template_day_line_ids.mapped('hora_inicio'), [9.0])

    def test_copy_week_to_next_week_returns_success_notification_and_reload(self):
        template = self._create_template(4, 2026)
        first_week = template.template_week_ids.sorted('sequence')[1]
        monday = first_week.template_day_ids.filtered(lambda day: day.weekday_index == 0)[:1]
        self.env['portalgestor.asignacion.mensual.dia.linea'].create({
            'template_day_id': monday.id,
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })

        action = first_week.action_copy_to_next_week()

        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(action['params']['next'], {'type': 'ir.actions.client', 'tag': 'reload'})

    def test_copy_week_to_next_week_warns_when_nothing_to_copy(self):
        template = self._create_template(4, 2026)
        first_week = template.template_week_ids.sorted('sequence')[1]

        action = first_week.action_copy_to_next_week()

        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('no tiene tramos', action['params']['message'])

    def test_copy_week_to_next_week_warns_when_there_is_no_next_week(self):
        template = self._create_template(4, 2026)
        last_week = template.template_week_ids.sorted('sequence')[-1]
        monday = last_week.template_day_ids.filtered(lambda day: day.weekday_index == 0)[:1]
        if monday:
            self.env['portalgestor.asignacion.mensual.dia.linea'].create({
                'template_day_id': monday.id,
                'hora_inicio': 8.0,
                'hora_fin': 10.0,
                'trabajador_id': self.worker_a.id,
            })

        action = last_week.action_copy_to_next_week()

        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('No hay una semana siguiente', action['params']['message'])

    def test_confirm_template_generates_confirmed_daily_assignments(self):
        template = self._create_template(4, 2026)
        first_week = template.template_week_ids.sorted('sequence')[1]
        monday = first_week.template_day_ids.filtered(lambda day: day.weekday_index == 0)[:1]
        friday = first_week.template_day_ids.filtered(lambda day: day.weekday_index == 4)[:1]

        self.env['portalgestor.asignacion.mensual.dia.linea'].create([
            {
                'template_day_id': monday.id,
                'hora_inicio': 8.0,
                'hora_fin': 10.0,
                'trabajador_id': self.worker_a.id,
            },
            {
                'template_day_id': friday.id,
                'hora_inicio': 12.0,
                'hora_fin': 14.0,
                'trabajador_id': self.worker_b.id,
            },
        ])

        template.action_verificar_y_confirmar()
        assignments = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario.id),
            ('fecha', 'in', [monday.fecha, friday.fecha]),
        ], order='fecha')

        self.assertEqual(assignments.mapped('confirmado'), [True, True])
        self.assertEqual(template.confirmado, True)
        self.assertEqual(sorted(assignments.mapped('lineas_ids.asignacion_mensual_dia_linea_id').ids), sorted(template.template_day_line_ids.ids))

    def test_discard_template_edit_keeps_previous_confirmed_schedule(self):
        template = self._create_template(4, 2026)
        monday = template.template_week_ids.sorted('sequence')[1].template_day_ids.filtered(lambda day: day.weekday_index == 0)[:1]
        monday_date = monday.fecha
        template_line = self.env['portalgestor.asignacion.mensual.dia.linea'].create({
            'template_day_id': monday.id,
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })
        template.action_verificar_y_confirmar()

        generated_line = self.env['portalgestor.asignacion.linea'].search([
            ('asignacion_mensual_id', '=', template.id),
            ('fecha', '=', monday.fecha),
        ], limit=1)
        self.assertEqual(generated_line.trabajador_id, self.worker_a)

        template.action_editar()
        template_line.write({'trabajador_id': self.worker_b.id})
        template.action_descartar_edicion()

        template.invalidate_recordset(['edit_session_pending'])
        generated_line.invalidate_recordset(['trabajador_id'])
        template_line.invalidate_recordset(['trabajador_id'])
        self.assertFalse(template.edit_session_pending)
        self.assertEqual(generated_line.trabajador_id, self.worker_a)
        self.assertEqual(
            template.template_day_ids.filtered(lambda day: day.fecha == monday_date).template_day_line_ids.trabajador_id,
            self.worker_a,
        )

    def test_same_day_warning_is_grouped_once_for_template(self):
        template = self._create_template(4, 2026)
        first_week = template.template_week_ids.sorted('sequence')[1]
        monday = first_week.template_day_ids.filtered(lambda day: day.weekday_index == 0)[:1]
        tuesday = first_week.template_day_ids.filtered(lambda day: day.weekday_index == 1)[:1]
        self.env['portalgestor.asignacion'].create({
            'usuario_id': self.other_user.id,
            'fecha': monday.fecha,
            'lineas_ids': [(0, 0, {'hora_inicio': 6.0, 'hora_fin': 8.0, 'trabajador_id': self.worker_a.id})],
        })
        self.env['portalgestor.asignacion'].create({
            'usuario_id': self.other_user.id,
            'fecha': tuesday.fecha,
            'lineas_ids': [(0, 0, {'hora_inicio': 6.0, 'hora_fin': 8.0, 'trabajador_id': self.worker_a.id})],
        })
        self.env['portalgestor.asignacion.mensual.dia.linea'].create([
            {
                'template_day_id': monday.id,
                'hora_inicio': 10.0,
                'hora_fin': 12.0,
                'trabajador_id': self.worker_a.id,
            },
            {
                'template_day_id': tuesday.id,
                'hora_inicio': 10.0,
                'hora_fin': 12.0,
                'trabajador_id': self.worker_a.id,
            },
        ])

        action = template.action_verificar_y_confirmar()
        wizard = self.env[action['res_model']].browse(action['res_id'])

        self.assertEqual(wizard.conflict_type, 'info_same_day')
        self.assertIn(fields.Date.to_string(monday.fecha), wizard.info_resumen)
        self.assertIn(fields.Date.to_string(tuesday.fecha), wizard.info_resumen)

    def test_confirm_template_reuses_matching_empty_line_without_missing_bucket(self):
        template = self._create_template(4, 2026)
        monday = template.template_week_ids.sorted('sequence')[1].template_day_ids.filtered(lambda day: day.weekday_index == 0)[:1]
        assignment = self.env['portalgestor.asignacion'].create({
            'usuario_id': self.usuario.id,
            'fecha': monday.fecha,
            'lineas_ids': [(0, 0, {'hora_inicio': 8.0, 'hora_fin': 10.0, 'trabajador_id': False})],
        })
        self.env['portalgestor.asignacion.mensual.dia.linea'].create({
            'template_day_id': monday.id,
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })

        template.action_verificar_y_confirmar()
        assignment.invalidate_recordset(['calendar_bucket_type'])

        self.assertEqual(assignment.calendar_bucket_type, 'completed')
        self.assertEqual(len(assignment.lineas_ids), 1)
        self.assertEqual(assignment.lineas_ids.trabajador_id, self.worker_a)
