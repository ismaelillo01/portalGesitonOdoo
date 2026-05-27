# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorTrabajoFijo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Trabajo Fijo V2',
            'code': 'ZONA_TRABAJO_FIJO_V2',
        })
        cls.usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Trabajo Fijo V2',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.worker_a = cls.env['trabajadores.trabajador'].create({
            'name': 'AP V2 A',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.worker_b = cls.env['trabajadores.trabajador'].create({
            'name': 'AP V2 B',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

    @classmethod
    def _create_fixed(cls):
        return cls._create_fixed_for('4', 2026)

    @classmethod
    def _create_fixed_for(cls, month, year):
        return cls.env['portalgestor.trabajo_fijo'].create({
            'usuario_id': cls.usuario.id,
            'month': str(month),
            'year': year,
        })

    def test_fixed_work_generates_confirmed_daily_assignments(self):
        fixed = self._create_fixed()
        self.assertEqual(fixed.fecha_inicio, fields.Date.to_date('2026-04-01'))
        self.assertEqual(fixed.fecha_fin, fields.Date.to_date('2026-04-30'))

        line = self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': fixed.id,
            'fecha': fields.Date.to_date('2026-04-06'),
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })

        fixed.action_verificar_y_confirmar()
        assignment = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario.id),
            ('fecha', '=', fields.Date.to_date('2026-04-06')),
        ], limit=1)

        self.assertTrue(assignment)
        self.assertTrue(assignment.confirmado)
        self.assertEqual(assignment.lineas_ids.trabajo_fijo_id, fixed)
        self.assertEqual(assignment.lineas_ids.trabajo_fijo_linea_id, line)
        self.assertEqual(assignment.lineas_ids.trabajador_id, self.worker_a)

    def test_vacation_releases_generated_fixed_work_day(self):
        fixed = self._create_fixed()
        template_line = self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': fixed.id,
            'fecha': fields.Date.to_date('2026-04-06'),
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })
        fixed.action_verificar_y_confirmar()
        generated_line = self.env['portalgestor.asignacion.linea'].search([
            ('trabajo_fijo_id', '=', fixed.id),
            ('fecha', '=', fields.Date.to_date('2026-04-06')),
        ], limit=1)
        self.assertEqual(generated_line.trabajador_id, self.worker_a)

        self.env['trabajadores.vacacion'].create({
            'trabajador_id': self.worker_a.id,
            'date_start': fields.Date.to_date('2026-04-06'),
            'date_stop': fields.Date.to_date('2026-04-06'),
        })

        generated_line.invalidate_recordset([
            'trabajador_id',
            'hora_inicio',
            'hora_fin',
            'trabajo_fijo_id',
            'trabajo_fijo_linea_id',
        ])
        self.assertFalse(generated_line.trabajador_id)
        self.assertEqual(generated_line.hora_inicio, 8.0)
        self.assertEqual(generated_line.hora_fin, 10.0)
        self.assertFalse(generated_line.trabajo_fijo_id)
        self.assertFalse(generated_line.trabajo_fijo_linea_id)
        self.assertEqual(template_line.trabajador_id, self.worker_a)

    def test_delete_fixed_work_returns_safe_navigation_action(self):
        fixed = self._create_fixed()

        action = fixed.action_eliminar_horario()

        self.assertFalse(fixed.exists())
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'portalgestor.trabajo_fijo')
        self.assertEqual(action.get('target'), 'current')

    def test_month_grid_accepts_unsaved_duplicate_time_lines(self):
        fixed = self.env['portalgestor.trabajo_fijo'].new({
            'usuario_id': self.usuario.id,
            'month': '4',
            'year': 2026,
            'line_ids': [
                (0, 0, {
                    'fecha': fields.Date.to_date('2026-04-06'),
                    'hora_inicio': 8.0,
                    'hora_fin': 10.0,
                    'trabajador_id': self.worker_a.id,
                }),
                (0, 0, {
                    'fecha': fields.Date.to_date('2026-04-06'),
                    'hora_inicio': 8.0,
                    'hora_fin': 10.0,
                    'trabajador_id': self.worker_b.id,
                }),
            ],
        })

        fixed._compute_month_grid_html()

        self.assertIn('AP V2 A', fixed.month_grid_html)
        self.assertIn('AP V2 B', fixed.month_grid_html)

    def test_seed_and_copy_week_work_from_parent_record(self):
        fixed = self._create_fixed()
        source_date = fields.Date.to_date('2026-04-06')
        self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': fixed.id,
            'fecha': source_date,
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })

        fixed.action_seed_week(source_date, [1, 4])
        self.assertEqual(
            fixed.line_ids.filtered(lambda line: line.fecha == fields.Date.to_date('2026-04-07')).trabajador_id,
            self.worker_a,
        )
        self.assertEqual(
            fixed.line_ids.filtered(lambda line: line.fecha == fields.Date.to_date('2026-04-10')).trabajador_id,
            self.worker_a,
        )

        action = fixed.action_copy_week_to_next(2)
        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['next']['type'], 'ir.actions.act_window_close')
        self.assertEqual(
            fixed.line_ids.filtered(lambda line: line.fecha == fields.Date.to_date('2026-04-13')).trabajador_id,
            self.worker_a,
        )
        self.assertEqual(
            fixed.line_ids.filtered(lambda line: line.fecha == fields.Date.to_date('2026-04-17')).trabajador_id,
            self.worker_a,
        )

    def test_copy_week_to_remaining_weeks_uses_same_source_week(self):
        fixed = self._create_fixed()
        self.env['portalgestor.trabajo_fijo.linea'].create([
            {
                'trabajo_fijo_id': fixed.id,
                'fecha': fields.Date.to_date('2026-04-06'),
                'hora_inicio': 8.0,
                'hora_fin': 10.0,
                'trabajador_id': self.worker_a.id,
            },
            {
                'trabajo_fijo_id': fixed.id,
                'fecha': fields.Date.to_date('2026-04-07'),
                'hora_inicio': 10.0,
                'hora_fin': 12.0,
                'trabajador_id': self.worker_b.id,
            },
        ])

        action = fixed.action_copy_week_to_remaining(2)

        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['params']['next']['type'], 'ir.actions.act_window_close')
        expected_days = {
            fields.Date.to_date('2026-04-13'): self.worker_a,
            fields.Date.to_date('2026-04-14'): self.worker_b,
            fields.Date.to_date('2026-04-20'): self.worker_a,
            fields.Date.to_date('2026-04-21'): self.worker_b,
            fields.Date.to_date('2026-04-27'): self.worker_a,
            fields.Date.to_date('2026-04-28'): self.worker_b,
        }
        for date_value, worker in expected_days.items():
            copied_lines = fixed.line_ids.filtered(lambda line: line.fecha == date_value)
            self.assertEqual(copied_lines.trabajador_id, worker)

    def test_month_summary_links_open_day_lines_with_default_date(self):
        fixed = self._create_fixed()

        self.assertIn('o_portalgestor_fixed_grid_day_link', fixed.month_grid_html)
        self.assertIn('data-date="2026-04-01"', fixed.month_grid_html)

        action = fixed.action_open_day_lines('2026-04-06')
        self.assertEqual(action['res_model'], 'portalgestor.trabajo_fijo.linea')
        self.assertEqual(action['target'], 'new')
        self.assertIn(('trabajo_fijo_id', '=', fixed.id), action['domain'])
        self.assertIn(('fecha', '=', '2026-04-06'), action['domain'])
        self.assertEqual(action['context']['default_trabajo_fijo_id'], fixed.id)
        self.assertEqual(action['context']['default_fecha'], '2026-04-06')
        self.assertNotIn('list_view_ref', action['context'])
        self.assertNotIn('search_view_ref', action['context'])

    def test_seed_and_copy_wizard_actions_include_form_views(self):
        fixed = self._create_fixed()

        seed_action = fixed.action_open_seed_wizard()
        copy_action = fixed.action_open_copy_week_wizard()
        with self.assertRaises(ValidationError):
            fixed.action_open_copy_year_wizard()

        self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': fixed.id,
            'fecha': fields.Date.to_date('2026-04-06'),
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })
        fixed.action_verificar_y_confirmar()
        copy_year_action = fixed.action_open_copy_year_wizard()

        self.assertEqual(seed_action['target'], 'new')
        self.assertEqual(seed_action['views'][0][1], 'form')
        self.assertTrue(seed_action['view_id'])
        self.assertEqual(copy_action['target'], 'new')
        self.assertEqual(copy_action['views'][0][1], 'form')
        self.assertTrue(copy_action['view_id'])
        self.assertEqual(copy_year_action['target'], 'new')
        self.assertEqual(copy_year_action['res_model'], 'portalgestor.trabajo_fijo.copy_year.wizard')
        self.assertFalse(copy_year_action['context']['default_month_4'])
        self.assertTrue(copy_year_action['context']['default_month_5'])
        self.assertTrue(copy_year_action['context']['default_month_12'])

    def test_copy_year_creates_confirmed_months_by_day_number_and_fills_extra_days(self):
        fixed = self._create_fixed_for('6', 2026)
        self.env['portalgestor.trabajo_fijo.linea'].create([
            {
                'trabajo_fijo_id': fixed.id,
                'fecha': fields.Date.to_date('2026-06-20'),
                'hora_inicio': 9.0,
                'hora_fin': 11.0,
                'trabajador_id': self.worker_b.id,
            },
            {
                'trabajo_fijo_id': fixed.id,
                'fecha': fields.Date.to_date('2026-06-24'),
                'hora_inicio': 8.0,
                'hora_fin': 10.0,
                'trabajador_id': self.worker_a.id,
            },
            {
                'trabajo_fijo_id': fixed.id,
                'fecha': fields.Date.to_date('2026-06-30'),
                'hora_inicio': 11.0,
                'hora_fin': 12.0,
                'trabajador_id': self.worker_b.id,
            },
        ])
        fixed.action_verificar_y_confirmar()

        wizard = self.env['portalgestor.trabajo_fijo.copy_year.wizard'].create({
            'trabajo_fijo_id': fixed.id,
            'month_7': True,
        })
        action = wizard.action_apply()

        self.assertEqual(action['type'], 'ir.actions.client')
        july = self.env['portalgestor.trabajo_fijo'].search([
            ('usuario_id', '=', self.usuario.id),
            ('month', '=', '7'),
            ('year', '=', 2026),
        ], limit=1)
        self.assertTrue(july.confirmado)
        self.assertEqual(july.line_ids.filtered(lambda line: line.hora_inicio == 8.0).mapped('fecha'), [
            fields.Date.to_date('2026-07-24'),
            fields.Date.to_date('2026-07-31'),
        ])
        self.assertEqual(july.line_ids.filtered(lambda line: line.hora_inicio == 9.0).fecha, fields.Date.to_date('2026-07-20'))
        self.assertEqual(july.line_ids.filtered(lambda line: line.hora_inicio == 11.0).mapped('fecha'), [
            fields.Date.to_date('2026-07-30'),
        ])
        self.assertTrue(july.asignacion_linea_ids)
        self.assertTrue(all(july.asignacion_linea_ids.mapped('asignacion_id.confirmado')))

    def test_copy_year_overwrites_existing_target_month(self):
        source = self._create_fixed_for('1', 2026)
        self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': source.id,
            'fecha': fields.Date.to_date('2026-01-05'),
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })
        source.action_verificar_y_confirmar()

        target = self._create_fixed_for('2', 2026)
        self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': target.id,
            'fecha': fields.Date.to_date('2026-02-03'),
            'hora_inicio': 14.0,
            'hora_fin': 16.0,
            'trabajador_id': self.worker_b.id,
        })
        target.action_verificar_y_confirmar()
        old_assignment_line = target.asignacion_linea_ids
        self.assertTrue(old_assignment_line)

        self.env['portalgestor.trabajo_fijo.copy_year.wizard'].create({
            'trabajo_fijo_id': source.id,
            'month_2': True,
        }).action_apply()

        target.invalidate_recordset(['line_ids', 'asignacion_linea_ids', 'confirmado'])
        self.assertTrue(target.confirmado)
        self.assertEqual(len(target.line_ids), 1)
        self.assertEqual(target.line_ids.fecha, fields.Date.to_date('2026-02-05'))
        self.assertEqual(target.line_ids.trabajador_id, self.worker_a)
        self.assertFalse(old_assignment_line.exists())

    def test_copy_year_rolls_back_all_months_when_one_target_fails(self):
        fixed = self._create_fixed_for('1', 2026)
        self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': fixed.id,
            'fecha': fields.Date.to_date('2026-01-05'),
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })
        fixed.action_verificar_y_confirmar()
        self.env['trabajadores.vacacion'].create({
            'trabajador_id': self.worker_a.id,
            'date_start': fields.Date.to_date('2026-03-05'),
            'date_stop': fields.Date.to_date('2026-03-05'),
        })

        wizard = self.env['portalgestor.trabajo_fijo.copy_year.wizard'].create({
            'trabajo_fijo_id': fixed.id,
            'month_2': True,
            'month_3': True,
        })
        with self.assertRaises(ValidationError):
            wizard.action_apply()

        february = self.env['portalgestor.trabajo_fijo'].search([
            ('usuario_id', '=', self.usuario.id),
            ('month', '=', '2'),
            ('year', '=', 2026),
        ])
        self.assertFalse(february)

    def test_open_day_lines_starts_safe_edit_session_for_confirmed_fixed(self):
        fixed = self._create_fixed()
        self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': fixed.id,
            'fecha': fields.Date.to_date('2026-04-06'),
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })
        fixed.action_verificar_y_confirmar()
        self.assertTrue(fixed.confirmado)
        self.assertFalse(fixed.edit_session_pending)

        fixed.action_open_day_lines('2026-04-06')

        fixed.invalidate_recordset(['edit_session_pending', 'edit_snapshot_data'])
        self.assertTrue(fixed.edit_session_pending)
        self.assertTrue(fixed.edit_snapshot_data)

    def test_reconfirm_reuses_generated_line_when_day_tramo_is_recreated(self):
        fixed = self._create_fixed()
        template_line = self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': fixed.id,
            'fecha': fields.Date.to_date('2026-04-06'),
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })
        fixed.action_verificar_y_confirmar()
        generated_line = self.env['portalgestor.asignacion.linea'].search([
            ('trabajo_fijo_id', '=', fixed.id),
            ('fecha', '=', fields.Date.to_date('2026-04-06')),
        ], limit=1)
        generated_line_id = generated_line.id

        fixed.action_editar()
        template_line.unlink()
        new_template_line = self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': fixed.id,
            'fecha': fields.Date.to_date('2026-04-06'),
            'hora_inicio': 9.0,
            'hora_fin': 11.0,
            'trabajador_id': self.worker_a.id,
        })
        fixed.action_verificar_y_confirmar()

        generated_line = self.env['portalgestor.asignacion.linea'].browse(generated_line_id)
        self.assertTrue(generated_line.exists())
        self.assertEqual(generated_line.hora_inicio, 9.0)
        self.assertEqual(generated_line.hora_fin, 11.0)
        self.assertEqual(generated_line.trabajo_fijo_linea_id, new_template_line)
        self.assertTrue(fixed.confirmado)
        self.assertFalse(fixed.edit_session_pending)

    def test_discard_edit_restores_confirmed_template_and_calendar(self):
        fixed = self._create_fixed()
        line = self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': fixed.id,
            'fecha': fields.Date.to_date('2026-04-06'),
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': self.worker_a.id,
        })
        fixed.action_verificar_y_confirmar()
        generated_line = self.env['portalgestor.asignacion.linea'].search([
            ('trabajo_fijo_id', '=', fixed.id),
            ('fecha', '=', fields.Date.to_date('2026-04-06')),
        ], limit=1)
        self.assertEqual(generated_line.trabajador_id, self.worker_a)

        fixed.action_editar()
        line.write({'trabajador_id': self.worker_b.id})
        fixed.action_descartar_edicion()

        generated_line.invalidate_recordset(['trabajador_id'])
        restored_line = fixed.line_ids.filtered(lambda item: item.fecha == fields.Date.to_date('2026-04-06'))
        self.assertFalse(fixed.edit_session_pending)
        self.assertTrue(fixed.confirmado)
        self.assertEqual(restored_line.trabajador_id, self.worker_a)
        self.assertEqual(generated_line.trabajador_id, self.worker_a)
