# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorUsuarioFaltaJustificada(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Falta Usuario',
            'code': 'ZONA_FALTA_USUARIO_TEST',
        })
        cls.usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Falta',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Falta Usuario',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

    @classmethod
    def _create_assignment(cls, date_value):
        return cls.env['portalgestor.asignacion'].create({
            'usuario_id': cls.usuario.id,
            'fecha': date_value,
            'lineas_ids': [(0, 0, {
                'hora_inicio': 8.0,
                'hora_fin': 10.0,
                'trabajador_id': cls.worker.id,
            })],
        })

    def test_user_justified_absence_cancels_assignments_inside_range(self):
        inside_date = fields.Date.to_date('2099-10-10')
        outside_date = fields.Date.to_date('2099-10-12')
        inside_assignment = self._create_assignment(inside_date)
        outside_assignment = self._create_assignment(outside_date)

        self.env['usuarios.falta.justificada'].create({
            'usuario_id': self.usuario.id,
            'fecha_inicio': inside_date,
            'fecha_fin': inside_date,
            'motivo': 'Ingreso hospitalario',
        })

        self.assertFalse(inside_assignment.exists())
        self.assertTrue(outside_assignment.exists())

    def test_user_justified_absence_write_cancels_new_range_without_restoring_previous_days(self):
        first_date = fields.Date.to_date('2099-10-15')
        second_date = fields.Date.to_date('2099-10-16')
        first_assignment = self._create_assignment(first_date)
        second_assignment = self._create_assignment(second_date)
        absence = self.env['usuarios.falta.justificada'].create({
            'usuario_id': self.usuario.id,
            'fecha_inicio': first_date,
            'fecha_fin': first_date,
        })

        absence.write({
            'fecha_inicio': second_date,
            'fecha_fin': second_date,
        })

        self.assertFalse(first_assignment.exists())
        self.assertFalse(second_assignment.exists())

    def test_user_justified_absence_blocks_manual_confirmation_on_absent_day(self):
        absence_date = fields.Date.to_date('2099-10-20')
        self.env['usuarios.falta.justificada'].create({
            'usuario_id': self.usuario.id,
            'fecha_inicio': absence_date,
            'fecha_fin': absence_date,
        })
        assignment = self._create_assignment(absence_date)

        with self.assertRaisesRegex(ValidationError, 'no necesita asistencia'):
            assignment.action_verificar_y_confirmar()

    def test_user_justified_absence_prevents_fixed_work_regeneration_for_absent_day(self):
        absent_date = fields.Date.to_date('2026-04-06')
        active_date = fields.Date.to_date('2026-04-07')
        fixed = self.env['portalgestor.trabajo_fijo'].create({
            'usuario_id': self.usuario.id,
            'month': '4',
            'year': 2026,
        })
        self.env['portalgestor.trabajo_fijo.linea'].create([
            {
                'trabajo_fijo_id': fixed.id,
                'fecha': absent_date,
                'hora_inicio': 8.0,
                'hora_fin': 10.0,
                'trabajador_id': self.worker.id,
            },
            {
                'trabajo_fijo_id': fixed.id,
                'fecha': active_date,
                'hora_inicio': 8.0,
                'hora_fin': 10.0,
                'trabajador_id': self.worker.id,
            },
        ])
        fixed.action_verificar_y_confirmar()
        absent_assignment = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario.id),
            ('fecha', '=', absent_date),
        ], limit=1)
        active_assignment = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario.id),
            ('fecha', '=', active_date),
        ], limit=1)
        self.assertTrue(absent_assignment)
        self.assertTrue(active_assignment)

        self.env['usuarios.falta.justificada'].create({
            'usuario_id': self.usuario.id,
            'fecha_inicio': absent_date,
            'fecha_fin': absent_date,
        })
        fixed.invalidate_recordset(['confirmado'])
        self.assertFalse(fixed.confirmado)
        self.assertFalse(absent_assignment.exists())
        self.assertTrue(active_assignment.exists())

        fixed.with_context(portalgestor_skip_trabajo_fijo_same_day_warning=True).action_verificar_y_confirmar()

        recreated_absent_assignment = self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario.id),
            ('fecha', '=', absent_date),
        ], limit=1)
        self.assertFalse(recreated_absent_assignment)
        self.assertTrue(self.env['portalgestor.asignacion'].search([
            ('usuario_id', '=', self.usuario.id),
            ('fecha', '=', active_date),
        ], limit=1))
