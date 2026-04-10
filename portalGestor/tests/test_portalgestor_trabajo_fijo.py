# -*- coding: utf-8 -*-
from odoo import fields
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
        return cls.env['portalgestor.trabajo_fijo'].create({
            'usuario_id': cls.usuario.id,
            'month': '4',
            'year': 2026,
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

        fixed.action_copy_week_to_next(2)
        self.assertEqual(
            fixed.line_ids.filtered(lambda line: line.fecha == fields.Date.to_date('2026-04-13')).trabajador_id,
            self.worker_a,
        )
        self.assertEqual(
            fixed.line_ids.filtered(lambda line: line.fecha == fields.Date.to_date('2026-04-17')).trabajador_id,
            self.worker_a,
        )

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
