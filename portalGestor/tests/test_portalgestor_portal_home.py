# -*- coding: utf-8 -*-

from pathlib import Path

from odoo import http
from odoo.modules.module import get_module_resource
from odoo.tests import tagged
from odoo.tests.common import HOST, HttpCase, Opener, TransactionCase, get_db_name, new_test_user


@tagged('-at_install', 'post_install')
class TestPortalGestorPortalHomeAction(TransactionCase):
    def test_new_internal_users_get_portal_home_action(self):
        expected_action = self.env.ref('portalGestor.action_portalgestor_portal_home')

        user = new_test_user(
            self.env,
            login='portal_home_new_user',
            password='portal_home_new_user',
            groups='base.group_user,gestores.group_gestores_agusto',
        )

        self.assertEqual(user.action_id.id, expected_action.id)

    def test_home_action_updater_reassigns_existing_internal_users(self):
        expected_action = self.env.ref('portalGestor.action_portalgestor_portal_home')
        user = new_test_user(
            self.env,
            login='portal_home_existing_user',
            password='portal_home_existing_user',
            groups='base.group_user,gestores.group_gestores_agusto',
        )
        user.action_id = False

        self.env['res.users'].set_portalgestor_home_action_for_internal_users()

        self.assertEqual(user.action_id.id, expected_action.id)


@tagged('-at_install', 'post_install')
class TestPortalGestorPortalRoutes(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager_user = new_test_user(
            cls.env,
            login='portal_home_manager',
            password='portal_home_manager',
            groups='base.group_user,gestores.group_gestores_agusto',
        )

    def setUp(self):
        super().setUp()
        self.session = http.root.session_store.new()
        self.session.update(http.get_default_session(), db=get_db_name())
        self.opener = Opener(self.env.cr)
        self.opener.cookies.set('session_id', self.session.sid, domain=HOST, path='/')

    def _login_internal_manager(self, redirect='/odoo'):
        post_data = {
            'login': 'portal_home_manager',
            'password': 'portal_home_manager',
            'csrf_token': http.Request.csrf_token(self),
        }
        if redirect is not None:
            post_data['redirect'] = redirect

        response = self.url_open('/web/login', data=post_data, allow_redirects=False)
        self.assertIn(response.status_code, (303, 200))
        return response

    def test_login_redirects_to_portal_home(self):
        response = self._login_internal_manager(redirect=None)
        location = response.headers.get('Location', '')

        self.assertEqual(response.status_code, 303)
        self.assertTrue(location.endswith('/portal-inicio'), location)

    def test_internal_portal_routes_require_authentication(self):
        self.opener.cookies.clear()

        for route in ('/portal-inicio', '/portal-ayuda'):
            response = self.url_open(route, allow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertIn('/web/login', response.headers.get('Location', ''))

    def test_internal_portal_pages_render_for_authenticated_user(self):
        self._login_internal_manager()

        home_response = self.url_open('/portal-inicio')
        self.assertEqual(home_response.status_code, 200)
        self.assertIn('Portal Gestor', home_response.text)
        self.assertIn('APs', home_response.text)
        self.assertIn('Usuarios', home_response.text)
        self.assertIn('Ayuda', home_response.text)
        self.assertIn('carousel-indicators', home_response.text)
        self.assertNotIn('data-bs-ride="carousel"', home_response.text)

        help_response = self.url_open('/portal-ayuda?category=usuarios')
        self.assertEqual(help_response.status_code, 200)
        self.assertIn('Centro de ayuda', help_response.text)
        self.assertIn('Como anadir un usuario', help_response.text)
        self.assertIn('Como saco el reporte mensual de un usuario', help_response.text)

    def test_backend_home_button_redirects_to_portal_home(self):
        js_path = Path(get_module_resource(
            'ui_brian_theme', 'static', 'src', 'js', 'navbar_home_button.js'
        ))
        xml_path = Path(get_module_resource(
            'ui_brian_theme', 'static', 'src', 'xml', 'navbar_home_button.xml'
        ))

        self.assertTrue(js_path.is_file())
        self.assertTrue(xml_path.is_file())

        js_source = js_path.read_text(encoding='utf-8')
        xml_source = xml_path.read_text(encoding='utf-8')

        self.assertIn('browser.location.href = "/portal-inicio";', js_source)
        self.assertIn('o_ui_brian_home_systray', xml_source)
        self.assertIn('goToPortalHome', xml_source)

    def test_portal_home_uses_safe_carousel_bootstrap(self):
        carousel_js_path = Path(get_module_resource(
            'ui_brian_theme', 'static', 'src', 'js', 'portal_internal_carousel.js'
        ))

        self.assertTrue(carousel_js_path.is_file())

        carousel_js_source = carousel_js_path.read_text(encoding='utf-8')
        self.assertIn('.o_portal_internal_carousel', carousel_js_source)
        self.assertIn('window.bootstrap', carousel_js_source)
        self.assertIn('replaceChildren', carousel_js_source)
