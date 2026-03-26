# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorManagerSovereignty(TransactionCase):
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
            'name': 'Zona Soberania',
            'code': 'ZONA_SOBERANIA',
        })

        cls.usuario_agusto = cls.env['usuarios.usuario'].create({
            'name': 'Maria',
            'apellido1': 'Agusto',
            'apellido2': 'Visible',
            'dni_nie': '11111111A',
            'telefono': '600111111',
            'direccion': 'Calle Agusto 1',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.usuario_agusto_secundario = cls.env['usuarios.usuario'].create({
            'name': 'Lucas',
            'apellido1': 'Agusto',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.usuario_intecum = cls.env['usuarios.usuario'].create({
            'name': 'Pablo',
            'apellido1': 'Intecum',
            'apellido2': 'Oculto',
            'dni_nie': '22222222B',
            'telefono': '600222222',
            'direccion': 'Calle Intecum 2',
            'grupo': 'intecum',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })

        cls.ap_agusto = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Agusto',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.ap_intecum = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Intecum',
            'grupo': 'intecum',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })

        cls.gestor_agusto_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Agusto',
            'login': 'gestor_agusto_soberania@test.local',
            'groups_id': [(6, 0, [cls.group_user.id, cls.group_agusto.id])],
        })
        cls.gestor_intecum_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Intecum',
            'login': 'gestor_intecum_soberania@test.local',
            'groups_id': [(6, 0, [cls.group_user.id, cls.group_intecum.id])],
        })

    @classmethod
    def _create_assignment(cls, usuario, fecha, line_specs):
        return cls.env['portalgestor.asignacion'].create({
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

    @classmethod
    def _create_fixed_assignment(cls, usuario, fecha_inicio, fecha_fin, line_specs):
        return cls.env['portalgestor.asignacion.mensual'].create({
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

    def test_agusto_can_read_all_users_but_intecum_data_is_masked(self):
        usuarios = self.env['usuarios.usuario'].with_user(self.gestor_agusto_user).search(
            [('id', 'in', [self.usuario_agusto.id, self.usuario_intecum.id])],
            order='id',
        )

        self.assertEqual(usuarios.ids, [self.usuario_agusto.id, self.usuario_intecum.id])
        masked_values = self.env['usuarios.usuario'].with_user(self.gestor_agusto_user).browse(
            self.usuario_intecum.id
        ).read(['name', 'apellido1', 'apellido2', 'dni_nie', 'telefono', 'direccion', 'grupo'])[0]
        self.assertRegex(masked_values['name'], r'^Usuario Intecum \d+$')
        self.assertEqual(masked_values['apellido1'], '')
        self.assertEqual(masked_values['apellido2'], '')
        self.assertEqual(masked_values['dni_nie'], '')
        self.assertEqual(masked_values['telefono'], '')
        self.assertEqual(masked_values['direccion'], '')
        self.assertEqual(masked_values['grupo'], 'intecum')

    def test_agusto_name_get_masks_intecum_user(self):
        label = self.env['usuarios.usuario'].with_user(self.gestor_agusto_user).browse(
            self.usuario_intecum.id
        ).name_get()[0][1]

        self.assertRegex(label, r'^Usuario Intecum \d+$')

    def test_agusto_can_read_all_workers(self):
        trabajadores = self.env['trabajadores.trabajador'].with_user(self.gestor_agusto_user).search(
            [('id', 'in', [self.ap_agusto.id, self.ap_intecum.id])],
            order='id',
        )

        self.assertEqual(trabajadores.ids, [self.ap_agusto.id, self.ap_intecum.id])

    def test_agusto_cannot_create_update_or_delete_intecum_users(self):
        with self.assertRaises(AccessError):
            self.env['usuarios.usuario'].with_user(self.gestor_agusto_user).create({
                'name': 'No Permitido',
                'grupo': 'intecum',
                'zona_trabajo_id': self.zone.id,
                'servicio_ids': [(6, 0, [self.ap_service.id])],
            })

        with self.assertRaises(AccessError):
            self.usuario_intecum.with_user(self.gestor_agusto_user).write({'telefono': '600333333'})

        with self.assertRaises(AccessError):
            self.usuario_intecum.with_user(self.gestor_agusto_user).unlink()

    def test_intecum_can_manage_users_from_both_groups(self):
        self.usuario_intecum.with_user(self.gestor_intecum_user).write({'telefono': '700000001'})
        self.usuario_agusto.with_user(self.gestor_intecum_user).write({'telefono': '700000002'})

        self.assertEqual(self.usuario_intecum.telefono, '700000001')
        self.assertEqual(self.usuario_agusto.telefono, '700000002')

    def test_agusto_cannot_manage_intecum_daily_assignment(self):
        fecha = fields.Date.to_date('2099-07-10')
        asignacion_intecum = self._create_assignment(
            self.usuario_intecum,
            fecha,
            [(8.0, 10.0, self.ap_intecum)],
        )

        asignaciones = self.env['portalgestor.asignacion'].with_user(self.gestor_agusto_user).search(
            [('id', '=', asignacion_intecum.id)]
        )
        self.assertEqual(asignaciones.ids, [asignacion_intecum.id])

        with self.assertRaises(AccessError):
            self.env['portalgestor.asignacion'].with_user(self.gestor_agusto_user).create({
                'usuario_id': self.usuario_intecum.id,
                'fecha': fecha,
                'lineas_ids': [(0, 0, {'hora_inicio': 10.0, 'hora_fin': 12.0, 'trabajador_id': self.ap_agusto.id})],
            })

        with self.assertRaises(AccessError):
            asignacion_intecum.with_user(self.gestor_agusto_user).write({'confirmado': True})

        with self.assertRaises(AccessError):
            asignacion_intecum.with_user(self.gestor_agusto_user).unlink()

    def test_agusto_cannot_manage_intecum_fixed_assignment(self):
        fecha = fields.Date.to_date('2099-07-11')
        trabajo_fijo = self._create_fixed_assignment(
            self.usuario_intecum,
            fecha,
            fecha,
            [(8.0, 10.0, self.ap_intecum)],
        )

        with self.assertRaises(AccessError):
            self.env['portalgestor.asignacion.mensual'].with_user(self.gestor_agusto_user).create({
                'usuario_id': self.usuario_intecum.id,
                'fecha_inicio': fecha,
                'fecha_fin': fecha,
                'linea_fija_ids': [(0, 0, {'hora_inicio': 8.0, 'hora_fin': 10.0, 'trabajador_id': self.ap_agusto.id})],
            })

        with self.assertRaises(AccessError):
            trabajo_fijo.with_user(self.gestor_agusto_user).write({'confirmado': True})

        with self.assertRaises(AccessError):
            trabajo_fijo.with_user(self.gestor_agusto_user).unlink()

    def test_calendar_bucket_records_mask_intecum_user_for_agusto(self):
        fecha = fields.Date.to_date('2099-07-12')
        asignacion = self._create_assignment(
            self.usuario_intecum,
            fecha,
            [(8.0, 10.0, self.ap_intecum)],
        )
        asignacion.write({'confirmado': True})

        records = self.env['portalgestor.asignacion'].with_user(self.gestor_agusto_user).get_calendar_bucket_records(
            fields.Date.to_string(fecha),
            'completed',
        )

        self.assertEqual(len(records), 1)
        self.assertRegex(records[0]['name'], r'^Usuario Intecum \d+$')
        self.assertFalse(records[0]['can_edit'])

    def test_assignment_name_get_masks_intecum_user_for_agusto(self):
        fecha = fields.Date.to_date('2099-07-13')
        asignacion = self._create_assignment(
            self.usuario_intecum,
            fecha,
            [(8.0, 10.0, self.ap_intecum)],
        )

        label = asignacion.with_user(self.gestor_agusto_user).name_get()[0][1]
        self.assertRegex(label, r'^Usuario Intecum \d+$')

    def test_agusto_cannot_override_intecum_overlap(self):
        fecha = fields.Date.to_date('2099-07-14')
        asignacion_intecum = self._create_assignment(
            self.usuario_intecum,
            fecha,
            [(8.0, 10.0, self.ap_intecum)],
        )
        asignacion_intecum.write({'confirmado': True})
        asignacion_agusto = self._create_assignment(
            self.usuario_agusto,
            fecha,
            [(9.0, 11.0, self.ap_intecum)],
        )

        action = asignacion_agusto.with_user(self.gestor_agusto_user).action_verificar_y_confirmar()
        self.assertEqual(action['res_model'], 'portalgestor.conflict.wizard')
        wizard = self.env[action['res_model']].with_user(self.gestor_agusto_user).browse(action['res_id'])
        self.assertEqual(wizard.conflict_type, 'protected_intecum_overlapping')
        with self.assertRaises(AccessError):
            wizard.action_confirm()
        bucket_records = self.env['portalgestor.asignacion'].with_user(
            self.gestor_agusto_user
        ).get_calendar_bucket_records(fields.Date.to_string(fecha), 'completed')
        self.assertEqual([record['id'] for record in bucket_records], [asignacion_intecum.id])
        self.assertFalse(asignacion_agusto.confirmado)

    def test_agusto_can_override_agusto_overlap(self):
        fecha = fields.Date.to_date('2099-07-15')
        asignacion_existente = self._create_assignment(
            self.usuario_agusto_secundario,
            fecha,
            [(8.0, 10.0, self.ap_agusto)],
        )
        asignacion_actual = self._create_assignment(
            self.usuario_agusto,
            fecha,
            [(9.0, 11.0, self.ap_agusto)],
        )

        action = asignacion_actual.with_user(self.gestor_agusto_user).action_verificar_y_confirmar()
        wizard = self.env[action['res_model']].with_user(self.gestor_agusto_user).browse(action['res_id'])
        self.assertEqual(wizard.conflict_type, 'overlapping')
        result = wizard.action_confirm()

        self.assertEqual(result['type'], 'ir.actions.act_window_close')
        self.assertFalse(asignacion_existente.lineas_ids.trabajador_id)
        self.assertTrue(asignacion_actual.confirmado)

    def test_assignment_web_read_masks_nested_user_display_name_for_agusto(self):
        fecha = fields.Date.to_date('2099-07-16')
        asignacion = self._create_assignment(
            self.usuario_intecum,
            fecha,
            [(8.0, 10.0, self.ap_intecum)],
        )

        result = asignacion.with_user(self.gestor_agusto_user).web_read({
            'usuario_id': {
                'context': {'portalgestor_viewer_uid': self.gestor_agusto_user.id},
                'fields': {
                    'display_name': {},
                },
            },
        })[0]

        self.assertRegex(result['usuario_id']['display_name'], r'^Usuario Intecum \d+$')

    def test_agusto_cannot_generate_user_reports_for_intecum(self):
        wizard = self.env['portalgestor.usuario.report.wizard'].with_user(
            self.gestor_agusto_user
        ).create({
            'usuario_ids': [(6, 0, [self.usuario_intecum.id])],
            'mes': '7',
            'anio': '2099',
            'formato_salida': 'pdf',
        })

        with self.assertRaises(AccessError):
            wizard.action_generate_report()

    def test_portalgestor_calendar_only_shows_confirmed_assignments(self):
        fecha = fields.Date.to_date('2099-07-17')
        asignacion_confirmada = self._create_assignment(
            self.usuario_agusto,
            fecha,
            [(8.0, 10.0, self.ap_agusto)],
        )
        asignacion_confirmada.write({'confirmado': True})
        self._create_assignment(
            self.usuario_agusto_secundario,
            fecha,
            [(10.0, 12.0, self.ap_intecum)],
        )

        summary = self.env['portalgestor.asignacion'].with_user(
            self.gestor_agusto_user
        ).get_calendar_bucket_summary(fields.Date.to_string(fecha), fields.Date.to_string(fecha))
        records = self.env['portalgestor.asignacion'].with_user(
            self.gestor_agusto_user
        ).get_calendar_bucket_records(fields.Date.to_string(fecha), 'completed')

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]['count'], 1)
        self.assertEqual([record['id'] for record in records], [asignacion_confirmada.id])

    def test_agusto_group_field_is_locked_and_new_users_default_to_agusto(self):
        values = self.usuario_agusto.with_user(self.gestor_agusto_user).read(
            ['group_selection_locked']
        )[0]
        self.assertTrue(values['group_selection_locked'])

        created_user = self.env['usuarios.usuario'].with_user(self.gestor_agusto_user).create({
            'name': 'Nuevo Agusto',
            'zona_trabajo_id': self.zone.id,
            'servicio_ids': [(6, 0, [self.ap_service.id])],
        })

        self.assertEqual(created_user.grupo, 'agusto')
