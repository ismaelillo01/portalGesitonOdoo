# -*- coding: utf-8 -*-
from datetime import date
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorUsuarioResumen(TransactionCase):
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
        cls.catering_comida_service = cls.env.ref('usuarios.usuarios_servicio_catering_comida')
        cls.catering_cena_service = cls.env.ref('usuarios.usuarios_servicio_catering_cena')
        cls.group_user = cls.env.ref('base.group_user')
        cls.group_agusto = cls.env.ref('gestores.group_gestores_agusto')
        cls.group_admin = cls.env.ref('gestores.group_gestores_administrador')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Resumen Usuarios',
            'code': 'ZONA_RESUMEN_USUARIOS',
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Resumen Usuarios',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

        cls.gestor_1_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Resumen Uno',
            'login': 'gestor_resumen_uno@test.local',
            'groups_id': [(6, 0, [cls.group_user.id])],
        })
        cls.gestor_2_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Resumen Dos',
            'login': 'gestor_resumen_dos@test.local',
            'groups_id': [(6, 0, [cls.group_user.id])],
        })
        cls.admin_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Resumen Admin',
            'login': 'gestor_resumen_admin@test.local',
            'groups_id': [(6, 0, [cls.group_user.id, cls.group_admin.id])],
        })
        cls.gestor_1 = cls.env['gestores.gestor'].create({
            'name': 'Gestor Resumen Uno',
            'grupo': 'agusto',
            'user_id': cls.gestor_1_user.id,
        })
        cls.gestor_2 = cls.env['gestores.gestor'].create({
            'name': 'Gestor Resumen Dos',
            'grupo': 'agusto',
            'user_id': cls.gestor_2_user.id,
        })

        cls.usuario_1 = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Resumen',
            'apellido1': 'Principal',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'gestor_id': cls.gestor_1.id,
            'servicio_ids': [
                (
                    6,
                    0,
                    [
                        cls.ap_service.id,
                        cls.catering_comida_service.id,
                        cls.catering_cena_service.id,
                    ],
                )
            ],
        })
        cls.usuario_2 = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Resumen',
            'apellido1': 'Secundario',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'gestor_id': cls.gestor_2.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })

    @classmethod
    def _create_assignment(cls, owner_user, usuario, assignment_date, line_specs):
        assignment = cls.env['portalgestor.asignacion'].with_user(owner_user).create({
            'usuario_id': usuario.id,
            'fecha': assignment_date,
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
        assignment.with_user(owner_user).action_verificar_y_confirmar()
        return assignment

    def _build_summary_lines(self, user):
        wizard = self.env['portalgestor.usuario.resumen.wizard'].with_user(user).create({
            'mes': '3',
            'anio': '2026',
        })
        action = wizard.action_view_summary()
        return self.env['portalgestor.usuario.resumen.line'].with_user(user).search(
            action['domain'],
            order='name, id',
        )

    def test_summary_generates_only_current_manager_users(self):
        self._create_assignment(
            self.gestor_1_user,
            self.usuario_1,
            fields.Date.to_date('2026-03-04'),
            [(8.0, 10.0, self.worker)],
        )
        self._create_assignment(
            self.gestor_2_user,
            self.usuario_2,
            fields.Date.to_date('2026-03-05'),
            [(8.0, 10.0, self.worker)],
        )

        lines = self._build_summary_lines(self.gestor_1_user)

        self.assertEqual(lines.mapped('usuario_id'), self.usuario_1)
        self.assertEqual(lines.ap_label, '2h')

    def test_summary_counts_all_hours_for_current_manager_users(self):
        self._create_assignment(
            self.gestor_1_user,
            self.usuario_1,
            fields.Date.to_date('2026-03-06'),
            [(8.0, 10.0, self.worker)],
        )
        self._create_assignment(
            self.admin_user,
            self.usuario_1,
            fields.Date.to_date('2026-03-07'),
            [(8.0, 9.0, self.worker)],
        )

        lines = self._build_summary_lines(self.gestor_1_user)

        self.assertEqual(lines.mapped('usuario_id'), self.usuario_1)
        self.assertEqual(lines.ap_total_minutes, 180)
        self.assertEqual(lines.ap_label, '3h')

    def test_summary_totals_computable_hours_and_catering(self):
        provider = self.env['usuarios.catering.proveedor'].create({
            'name': 'Proveedor Resumen',
        })
        comida_config = self.env['usuarios.catering.config'].create({
            'usuario_id': self.usuario_1.id,
            'service_code': 'catering_comida',
            'proveedor_id': provider.id,
            'date_start': date(2026, 3, 1),
            'lunes': True,
        })
        self.env['usuarios.catering.config'].create({
            'usuario_id': self.usuario_1.id,
            'service_code': 'catering_cena',
            'proveedor_id': provider.id,
            'date_start': date(2026, 3, 1),
            'martes': True,
        })
        self.env['usuarios.catering.suspension'].create({
            'config_id': comida_config.id,
            'date_start': date(2026, 3, 9),
            'date_stop': date(2026, 3, 9),
            'name': 'Suspension prueba',
        })
        assignment_date = fields.Date.to_date('2026-03-10')
        assignment = self._create_assignment(
            self.gestor_1_user,
            self.usuario_1,
            assignment_date,
            [(8.0, 12.0, self.worker)],
        )
        self.env['trabajadores.falta.justificada'].create({
            'trabajador_id': self.worker.id,
            'fecha': assignment_date,
            'hora_inicio': 9.0,
            'hora_fin': 10.0,
            'motivo': 'Consulta medica',
        }).action_verificar()
        assignment.lineas_ids.invalidate_recordset()

        line = self._build_summary_lines(self.gestor_1_user)

        self.assertEqual(line.ap_total_minutes, 180)
        self.assertEqual(line.ap_label, '3h')
        self.assertEqual(line.proveedor, 'Proveedor Resumen')
        self.assertEqual(line.catering_comida_count, 4)
        self.assertEqual(line.catering_cena_count, 5)

    def test_admin_summary_includes_all_users(self):
        lines = self._build_summary_lines(self.admin_user)

        self.assertIn(self.usuario_1, lines.mapped('usuario_id'))
        self.assertIn(self.usuario_2, lines.mapped('usuario_id'))
