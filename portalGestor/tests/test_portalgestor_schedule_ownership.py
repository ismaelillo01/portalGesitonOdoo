# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorScheduleOwnership(TransactionCase):
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
        cls.group_admin = cls.env.ref('gestores.group_gestores_administrador')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Ownership',
            'code': 'OWNERSHIP_ZONE',
        })

        cls.usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Ownership',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.usuario_secundario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Ownership 2',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.worker_a = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Ownership A',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.worker_b = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Ownership B',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

        cls.gestor_1 = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Uno',
            'login': 'gestor_uno_ownership@test.local',
            'groups_id': [(6, 0, [cls.group_user.id, cls.group_agusto.id])],
        })
        cls.gestor_2 = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Dos',
            'login': 'gestor_dos_ownership@test.local',
            'groups_id': [(6, 0, [cls.group_user.id, cls.group_agusto.id])],
        })
        cls.gestor_admin = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Admin Ownership',
            'login': 'gestor_admin_ownership@test.local',
            'groups_id': [(6, 0, [cls.group_user.id, cls.group_admin.id])],
        })

    @classmethod
    def _create_assignment(cls, owner_user, usuario, fecha, line_specs):
        return cls.env['portalgestor.asignacion'].with_user(owner_user).create({
            'usuario_id': usuario.id,
            'fecha': fecha,
            'lineas_ids': [
                (
                    0,
                    0,
                    {
                        'hora_inicio': hora_inicio,
                        'hora_fin': hora_fin,
                        'trabajador_id': trabajador.id,
                    },
                )
                for hora_inicio, hora_fin, trabajador in line_specs
            ],
        })

    @classmethod
    def _create_fixed_assignment(cls, owner_user, usuario, fecha_inicio, fecha_fin, line_specs):
        return cls.env['portalgestor.asignacion.mensual'].with_user(owner_user).create({
            'usuario_id': usuario.id,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'linea_fija_ids': [
                (
                    0,
                    0,
                    {
                        'hora_inicio': hora_inicio,
                        'hora_fin': hora_fin,
                        'trabajador_id': trabajador.id,
                    },
                )
                for hora_inicio, hora_fin, trabajador in line_specs
            ],
        })

    def test_daily_assignment_owner_transfers_on_reconfirmation(self):
        fecha = fields.Date.to_date('2099-09-01')
        asignacion = self._create_assignment(
            self.gestor_1,
            self.usuario,
            fecha,
            [(8.0, 10.0, self.worker_a)],
        )

        asignacion.with_user(self.gestor_1).action_verificar_y_confirmar()
        asignacion.invalidate_recordset(['gestor_owner_id'])
        asignacion.lineas_ids.invalidate_recordset(['gestor_owner_id'])

        self.assertEqual(asignacion.gestor_owner_id, self.gestor_1)
        self.assertEqual(asignacion.lineas_ids.gestor_owner_id, self.gestor_1)

        asignacion.with_user(self.gestor_2).action_editar()
        asignacion.with_user(self.gestor_2).write({
            'lineas_ids': [(1, asignacion.lineas_ids.id, {'hora_inicio': 9.0, 'hora_fin': 11.0})],
        })
        asignacion.with_user(self.gestor_2).action_verificar_y_confirmar()
        asignacion.invalidate_recordset(['gestor_owner_id'])
        asignacion.lineas_ids.invalidate_recordset(['gestor_owner_id'])

        self.assertEqual(asignacion.gestor_owner_id, self.gestor_2)
        self.assertEqual(asignacion.lineas_ids.gestor_owner_id, self.gestor_2)

    def test_fixed_assignment_confirmation_transfers_generated_assignment_owner(self):
        fecha_inicio = fields.Date.to_date('2099-09-02')
        fecha_fin = fields.Date.to_date('2099-09-03')
        trabajo_fijo = self._create_fixed_assignment(
            self.gestor_1,
            self.usuario,
            fecha_inicio,
            fecha_fin,
            [(8.0, 10.0, self.worker_a)],
        )

        trabajo_fijo.with_user(self.gestor_1).action_verificar_y_confirmar()
        generated_assignments = trabajo_fijo.asignacion_linea_ids.mapped('asignacion_id').exists()
        generated_assignments.invalidate_recordset(['gestor_owner_id'])
        self.assertTrue(generated_assignments)
        self.assertEqual(set(generated_assignments.mapped('gestor_owner_id').ids), {self.gestor_1.id})

        trabajo_fijo.with_user(self.gestor_2).action_editar()
        trabajo_fijo.with_user(self.gestor_2).write({
            'linea_fija_ids': [(1, trabajo_fijo.linea_fija_ids.id, {'trabajador_id': self.worker_b.id})],
        })
        trabajo_fijo.with_user(self.gestor_2).action_verificar_y_confirmar()
        generated_assignments.invalidate_recordset(['gestor_owner_id'])

        self.assertEqual(set(generated_assignments.mapped('gestor_owner_id').ids), {self.gestor_2.id})

    def test_calendar_bucket_summary_and_records_can_be_filtered_to_current_owner(self):
        fecha = fields.Date.to_date('2099-09-04')
        asignacion_gestor_1 = self._create_assignment(
            self.gestor_1,
            self.usuario,
            fecha,
            [(8.0, 10.0, self.worker_a)],
        )
        asignacion_gestor_1.with_user(self.gestor_1).action_verificar_y_confirmar()
        asignacion_gestor_2 = self._create_assignment(
            self.gestor_2,
            self.usuario_secundario,
            fecha,
            [(10.0, 12.0, self.worker_b)],
        )
        asignacion_gestor_2.with_user(self.gestor_2).action_verificar_y_confirmar()

        summary_all = self.env['portalgestor.asignacion'].with_user(
            self.gestor_1
        ).get_calendar_bucket_summary(
            fields.Date.to_string(fecha),
            fields.Date.to_string(fecha),
        )
        summary_mine = self.env['portalgestor.asignacion'].with_user(
            self.gestor_1
        ).with_context(
            portalgestor_only_my_schedules=True
        ).get_calendar_bucket_summary(
            fields.Date.to_string(fecha),
            fields.Date.to_string(fecha),
        )
        records_mine = self.env['portalgestor.asignacion'].with_user(
            self.gestor_1
        ).with_context(
            portalgestor_only_my_schedules=True
        ).get_calendar_bucket_records(
            fields.Date.to_string(fecha),
            'completed',
        )

        self.assertEqual(summary_all[0]['count'], 2)
        self.assertEqual(summary_mine[0]['count'], 1)
        self.assertEqual([record['id'] for record in records_mine], [asignacion_gestor_1.id])
        self.assertEqual(records_mine[0]['gestor_name'], self.gestor_1.name)

    def test_report_wizard_filters_workers_and_lines_by_owner_for_non_admin(self):
        fecha_gestor_1 = fields.Date.to_date('2099-09-05')
        fecha_gestor_2 = fields.Date.to_date('2099-09-06')
        fecha_worker_b = fields.Date.to_date('2099-09-07')
        self._create_assignment(
            self.gestor_1,
            self.usuario,
            fecha_gestor_1,
            [(8.0, 10.0, self.worker_a)],
        ).with_user(self.gestor_1).action_verificar_y_confirmar()
        self._create_assignment(
            self.gestor_2,
            self.usuario_secundario,
            fecha_gestor_2,
            [(10.0, 12.0, self.worker_a)],
        ).with_user(self.gestor_2).action_verificar_y_confirmar()
        self._create_assignment(
            self.gestor_2,
            self.usuario_secundario,
            fecha_worker_b,
            [(12.0, 14.0, self.worker_b)],
        ).with_user(self.gestor_2).action_verificar_y_confirmar()

        wizard = self.env['portalgestor.report.wizard'].with_user(self.gestor_1).create({
            'mes': '9',
            'anio': '2099',
        })
        wizard._compute_available_trabajador_ids()
        lines = wizard._get_report_lines_for_worker(self.worker_a)

        self.assertEqual(wizard.available_trabajador_ids, self.worker_a)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.gestor_owner_id, self.gestor_1)

        wizard.exportar_todos = True
        self.assertEqual(wizard._get_selected_workers(), self.worker_a)

        forbidden_wizard = self.env['portalgestor.report.wizard'].with_user(self.gestor_1).create({
            'mes': '9',
            'anio': '2099',
            'trabajador_ids': [(6, 0, [self.worker_b.id])],
        })
        with self.assertRaises(AccessError):
            forbidden_wizard.action_print_report()

    def test_report_wizard_admin_can_export_all_worker_lines(self):
        fecha_gestor_1 = fields.Date.to_date('2099-09-08')
        fecha_gestor_2 = fields.Date.to_date('2099-09-09')
        self._create_assignment(
            self.gestor_1,
            self.usuario,
            fecha_gestor_1,
            [(8.0, 10.0, self.worker_a)],
        ).with_user(self.gestor_1).action_verificar_y_confirmar()
        self._create_assignment(
            self.gestor_2,
            self.usuario_secundario,
            fecha_gestor_2,
            [(10.0, 12.0, self.worker_a)],
        ).with_user(self.gestor_2).action_verificar_y_confirmar()

        wizard = self.env['portalgestor.report.wizard'].with_user(self.gestor_admin).create({
            'mes': '9',
            'anio': '2099',
            'trabajador_ids': [(6, 0, [self.worker_a.id])],
        })
        lines = wizard._get_report_lines_for_worker(self.worker_a)

        self.assertEqual(len(lines), 2)
        self.assertEqual(sorted(lines.mapped('gestor_owner_id.id')), sorted([self.gestor_1.id, self.gestor_2.id]))
