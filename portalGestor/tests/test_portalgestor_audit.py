# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorAuditLog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.avatar_svg_patcher = patch(
            'odoo.addons.base.models.avatar_mixin.AvatarMixin._avatar_generate_svg',
            lambda self: False,
        )
        cls.avatar_svg_patcher.start()
        cls.addClassCleanup(cls.avatar_svg_patcher.stop)
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.group_user = cls.env.ref('base.group_user')
        cls.group_agusto = cls.env.ref('gestores.group_gestores_agusto')
        cls.group_intecum = cls.env.ref('gestores.group_gestores_intecum')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Auditoria',
            'code': 'ZONA_AUDITORIA',
        })
        cls.usuario = cls.env['usuarios.usuario'].create({
            'name': 'Susana Auditoria',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.usuario_intecum = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Intecum Auditoria',
            'grupo': 'intecum',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'Raquel Auditoria',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.gestor_agusto = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Agusto Auditoria',
            'login': 'gestor_agusto_auditoria@test.local',
            'groups_id': [(6, 0, [cls.group_user.id, cls.group_agusto.id])],
        })
        cls.gestor_intecum = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Intecum Auditoria',
            'login': 'gestor_intecum_auditoria@test.local',
            'groups_id': [(6, 0, [cls.group_user.id, cls.group_intecum.id])],
        })

    def _audit_logs(self, usuario=False, action_type=False, target_type=False):
        domain = []
        if usuario:
            domain.append(('usuario_name', 'ilike', usuario.name))
        if action_type:
            domain.append(('action_type', '=', action_type))
        if target_type:
            domain.append(('target_type', '=', target_type))
        return self.env['portalgestor.audit.log'].search(domain, order='event_datetime, id')

    def test_daily_schedule_audit_lifecycle_is_legible(self):
        assignment = self.env['portalgestor.asignacion'].create({
            'usuario_id': self.usuario.id,
            'fecha': fields.Date.to_date('2026-06-15'),
            'lineas_ids': [(0, 0, {
                'hora_inicio': 9.0,
                'hora_fin': 11.0,
                'trabajador_id': self.worker.id,
            })],
        })

        self.assertTrue(self._audit_logs(self.usuario, 'create', 'daily_assignment'))
        add_line_log = self._audit_logs(self.usuario, 'add_line', 'daily_line')[-1]
        self.assertIn('09:00-11:00', add_line_log.summary)
        self.assertIn('Raquel Auditoria', add_line_log.summary)
        self.assertNotIn(str(assignment.id), add_line_log.summary)

        assignment.action_verificar_y_confirmar()
        self.assertIn('confirmo horario de Susana Auditoria del 15/06/2026', self._audit_logs(
            self.usuario,
            'confirm',
            'daily_assignment',
        )[-1].summary)

        assignment.action_editar()
        self.assertTrue(self._audit_logs(self.usuario, 'edit', 'daily_assignment'))

        assignment.lineas_ids.write({'trabajador_id': False})
        release_log = self._audit_logs(self.usuario, 'release', 'daily_line')[-1]
        self.assertIn('libero el AP Raquel Auditoria', release_log.summary)
        self.assertIn('Susana Auditoria', release_log.summary)

        assignment.action_eliminar_horario()
        delete_log = self._audit_logs(self.usuario, 'delete', 'daily_assignment')[-1]
        self.assertIn('elimino horario de Susana Auditoria del 15/06/2026', delete_log.summary)
        self.assertFalse(assignment.exists())

    def test_fixed_work_audit_lifecycle_is_legible(self):
        fixed = self.env['portalgestor.trabajo_fijo'].create({
            'usuario_id': self.usuario.id,
            'month': '6',
            'year': 2026,
        })
        line = self.env['portalgestor.trabajo_fijo.linea'].create({
            'trabajo_fijo_id': fixed.id,
            'fecha': fields.Date.to_date('2026-06-15'),
            'hora_inicio': 9.0,
            'hora_fin': 11.0,
            'trabajador_id': self.worker.id,
        })

        create_log = self._audit_logs(self.usuario, 'create', 'fixed_work')[-1]
        self.assertIn('trabajo fijo de Susana Auditoria de junio 2026', create_log.summary)
        self.assertTrue(self._audit_logs(self.usuario, 'add_line', 'fixed_work_line'))

        fixed.action_verificar_y_confirmar()
        self.assertTrue(self._audit_logs(self.usuario, 'confirm', 'fixed_work'))

        fixed.action_editar()
        line.unlink()
        self.assertTrue(self._audit_logs(self.usuario, 'delete', 'fixed_work_line'))

        fixed.action_eliminar_horario()
        delete_log = self._audit_logs(self.usuario, 'delete', 'fixed_work')[-1]
        self.assertIn('elimino trabajo fijo de Susana Auditoria de junio 2026', delete_log.summary)

    def test_legacy_fixed_work_delete_keeps_readable_user_and_dates(self):
        legacy = self.env['portalgestor.asignacion.mensual'].create({
            'usuario_id': self.usuario.id,
            'fecha_inicio': fields.Date.to_date('2026-06-01'),
            'fecha_fin': fields.Date.to_date('2026-06-30'),
            'linea_fija_ids': [(0, 0, {
                'hora_inicio': 9.0,
                'hora_fin': 11.0,
                'trabajador_id': self.worker.id,
            })],
        })

        self.assertTrue(self._audit_logs(self.usuario, 'create', 'legacy_fixed'))
        legacy.action_eliminar_horario()
        delete_log = self._audit_logs(self.usuario, 'delete', 'legacy_fixed')[-1]
        self.assertIn('elimino trabajo fijo legacy de Susana Auditoria', delete_log.summary)
        self.assertIn('01/06/2026 - 30/06/2026', delete_log.summary)

    def test_audit_visibility_respects_gestor_group_scope(self):
        audit = self.env['portalgestor.audit.log']
        audit.create_event(
            'delete',
            'daily_assignment',
            'Gestor Admin elimino horario de Susana Auditoria del 15/06/2026',
            usuario=self.usuario,
            usuario_name=self.usuario.name,
            usuario_grupo=self.usuario.grupo,
        )
        audit.create_event(
            'delete',
            'daily_assignment',
            'Gestor Admin elimino horario de Usuario Intecum Auditoria del 15/06/2026',
            usuario=self.usuario_intecum,
            usuario_name=self.usuario_intecum.name,
            usuario_grupo=self.usuario_intecum.grupo,
        )

        agusto_logs = audit.with_user(self.gestor_agusto).search([('summary', 'ilike', 'Auditoria')])
        self.assertIn(self.usuario.name, agusto_logs.mapped('usuario_name'))
        self.assertNotIn(self.usuario_intecum.name, agusto_logs.mapped('usuario_name'))

        intecum_logs = audit.with_user(self.gestor_intecum).search([('summary', 'ilike', 'Auditoria')])
        self.assertIn(self.usuario.name, intecum_logs.mapped('usuario_name'))
        self.assertIn(self.usuario_intecum.name, intecum_logs.mapped('usuario_name'))

    def test_audit_records_are_readonly_from_ui_permissions(self):
        log = self.env['portalgestor.audit.log'].create_event(
            'create',
            'daily_assignment',
            'Gestor Admin creo horario de Susana Auditoria del 15/06/2026',
            usuario=self.usuario,
            usuario_name=self.usuario.name,
            usuario_grupo=self.usuario.grupo,
        )

        with self.assertRaises(AccessError):
            log.write({'summary': 'No permitido'})
        with self.assertRaises(AccessError):
            log.unlink()
