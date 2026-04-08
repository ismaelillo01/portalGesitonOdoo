# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalGestorUserManagerPriority(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.avatar_svg_patcher = patch(
            'odoo.addons.base.models.avatar_mixin.AvatarMixin._avatar_generate_svg',
            lambda self: False,
        )
        cls.avatar_svg_patcher.start()
        cls.addClassCleanup(cls.avatar_svg_patcher.stop)

        cls.group_user = cls.env.ref('base.group_user')
        cls.group_agusto = cls.env.ref('gestores.group_gestores_agusto')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona User Priority',
            'code': 'USER_PRIORITY_ZONE',
        })
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')

        cls.gestor_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Prioridad',
            'login': 'gestor_prioridad@test.local',
            'groups_id': [(6, 0, [cls.group_user.id, cls.group_agusto.id])],
        })
        cls.other_gestor_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Gestor Otro',
            'login': 'gestor_otro_prioridad@test.local',
            'groups_id': [(6, 0, [cls.group_user.id, cls.group_agusto.id])],
        })

        cls.gestor_record = cls.env['gestores.gestor'].sudo().create({
            'name': 'Gestor Prioridad',
            'grupo': 'agusto',
            'user_id': cls.gestor_user.id,
        })
        cls.other_gestor_record = cls.env['gestores.gestor'].sudo().create({
            'name': 'Gestor Otro',
            'grupo': 'agusto',
            'user_id': cls.other_gestor_user.id,
        })

        cls.my_usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Mio',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
            'gestor_id': cls.gestor_record.id,
        })
        cls.other_usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Otro',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
            'gestor_id': cls.other_gestor_record.id,
        })

    def test_user_selector_prioritizes_current_manager_users(self):
        selector_model = self.env['usuarios.usuario'].with_user(self.gestor_user).with_context(
            portalgestor_user_selector=True,
            portalgestor_viewer_uid=self.gestor_user.id,
        )
        results = selector_model.name_search('Usuario', limit=10)

        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0][0], self.my_usuario.id)
        self.assertEqual(results[1][0], self.other_usuario.id)

        web_results = selector_model.web_search_read(
            [('id', 'in', [self.my_usuario.id, self.other_usuario.id])],
            {'display_name': {}},
            limit=10,
        )
        self.assertEqual(
            [record['id'] for record in web_results['records'][:2]],
            [self.my_usuario.id, self.other_usuario.id],
        )
