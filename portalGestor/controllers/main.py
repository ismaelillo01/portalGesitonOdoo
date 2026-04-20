# -*- coding: utf-8 -*-

from copy import deepcopy

from odoo import http
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.http import request


PORTAL_HELP_CATEGORIES = [
    {
        'key': 'horarios',
        'label': 'Horarios',
        'summary': 'Gestion diaria, trabajos fijos y resolucion de conflictos.',
        'items': [
            {
                'question': 'Como anadir un horario diario?',
                'answer': (
                    'Entra en Portal Gestor, pulsa "Nuevo", elige el usuario, revisa la fecha '
                    'y anade los tramos horarios. Cuando tengas claro el reparto, asigna los APs '
                    'y guarda antes de verificar.'
                ),
            },
            {
                'question': 'Como verifico y confirmo un horario?',
                'answer': (
                    'Con el horario completo, usa "Verificar y Confirmar". Si aparece un aviso, '
                    'corrige primero los solapes o las restricciones que indique el sistema y '
                    'vuelve a intentarlo.'
                ),
            },
            {
                'question': 'Como modifico o elimino un horario ya creado?',
                'answer': (
                    'Busca el registro desde el calendario o desde la lista, abre la asignacion '
                    'y pulsa "Modificar Horario" para editarla. Si ese horario ya no debe existir, '
                    'usa "Eliminar Horario" desde la propia ficha.'
                ),
            },
            {
                'question': 'Como creo un trabajo fijo?',
                'answer': (
                    'Abre "Trabajos Fijos", crea el mes del usuario y rellena los tramos del mes. '
                    'Si te resulta mas comodo, entra desde el resumen mensual para abrir cada dia '
                    'con la fecha ya preparada.'
                ),
            },
            {
                'question': 'Como edito todos los dias de un trabajo fijo?',
                'answer': (
                    'Dentro del trabajo fijo usa "Sembrar desde un dia" para copiar tramos a otros '
                    'dias de la misma semana, o "Copiar semana" para repetir una semana completa '
                    'en la siguiente o en el resto del mes.'
                ),
            },
            {
                'question': 'Que hago si aparece un conflicto de AP?',
                'answer': (
                    'El asistente de conflictos te dira si el solape se puede ajustar o si esta '
                    'protegido por una regla de gestion. Revisa el tramo, cambia el AP o confirma '
                    'solo cuando el sistema te deje seguir.'
                ),
            },
        ],
    },
    {
        'key': 'aps',
        'label': 'APs',
        'summary': 'Alta, mantenimiento, vacaciones y consulta de disponibilidad.',
        'items': [
            {
                'question': 'Como anadir un AP?',
                'answer': (
                    'Entra en APs, crea el registro con sus datos personales y laborales, define '
                    'grupo y zonas de trabajo y guarda. En cuanto quede activo, ya podra salir en '
                    'los horarios y trabajos fijos.'
                ),
            },
            {
                'question': 'Como edito o doy de baja un AP?',
                'answer': (
                    'Abre su ficha desde la lista de APs, cambia los datos que necesites y guarda. '
                    'Si ya no debe entrar en nuevas asignaciones, marca la baja desde su registro.'
                ),
            },
            {
                'question': 'Como registro vacaciones de un AP?',
                'answer': (
                    'En "Vacaciones AP" crea el periodo de ausencia y guarda. A partir de ahi, '
                    'el sistema tendra en cuenta esas fechas para no proponer ese AP en horarios '
                    'o trabajos fijos.'
                ),
            },
            {
                'question': 'Como consulto el horario mensual de un AP?',
                'answer': (
                    'Si ves "Consultar horario" en el menu lateral, entra ahi, busca el AP y abre '
                    'su calendario mensual para revisar servicios, dias libres y vacaciones.'
                ),
            },
        ],
    },
    {
        'key': 'usuarios',
        'label': 'Usuarios',
        'summary': 'Creacion, edicion, servicios AP y reportes mensuales.',
        'items': [
            {
                'question': 'Como anadir un usuario?',
                'answer': (
                    'Desde Usuarios crea la ficha y completa sus datos. Antes de guardar, revisa '
                    'grupo, zona de trabajo, gestor y servicios para que luego aparezca bien en '
                    'los modulos de planificacion.'
                ),
            },
            {
                'question': 'Como hago que un usuario pueda recibir APs?',
                'answer': (
                    'En la ficha del usuario anade el servicio AP dentro de "Servicios". Solo los '
                    'usuarios con ese servicio quedaran disponibles para horarios y trabajos fijos.'
                ),
            },
            {
                'question': 'Como edito un usuario existente?',
                'answer': (
                    'Abre el usuario desde la lista, ajusta sus datos de contacto, asignacion o '
                    'estado y guarda los cambios. Si algo aparece bloqueado, revisa si depende del '
                    'grupo del gestor o del estado actual del usuario.'
                ),
            },
            {
                'question': 'Como saco el reporte mensual de un usuario?',
                'answer': (
                    'Desde la ficha del usuario pulsa "Horario usuario", elige mes, ano y formato '
                    'de salida y genera el reporte del periodo que necesites.'
                ),
            },
            {
                'question': 'Como exporto horarios de varios usuarios?',
                'answer': (
                    'En Usuarios > Reportes abre "Exportar Horario Usuarios", selecciona los '
                    'usuarios que te interesen o exporta todos los activos, y genera el archivo '
                    'del mes que quieras sacar.'
                ),
            },
        ],
    },
]


class PortalGestorLoginController(AuthSignupHome):

    @http.route()
    def web_login(self, redirect=None, **kw):
        response = super().web_login(redirect=redirect, **kw)
        if request.httprequest.method != 'POST' or redirect or not request.session.uid:
            return response

        user = request.env(user=request.session.uid)['res.users'].browse(request.session.uid)
        if user.has_group('base.group_user'):
            return request.redirect('/portal-inicio', 303)
        return response


class PortalGestorInternalController(http.Controller):

    def _get_visible_menu_ids(self):
        debug = bool(getattr(request.session, 'debug', False))
        return request.env['ir.ui.menu']._visible_menu_ids(debug)

    def _build_menu_link(self, key, label, menu_xmlid, description):
        menu = request.env.ref(menu_xmlid, raise_if_not_found=False)
        if not menu or menu.id not in self._get_visible_menu_ids() or not menu.action:
            return None

        action = menu.action.sudo()
        if action._name == 'ir.actions.act_url':
            url = action.url
        else:
            url = '/odoo/action-%s?menu_id=%s' % (action.id, menu.id)

        return {
            'key': key,
            'label': label,
            'description': description,
            'url': url,
        }

    def _get_link_map(self):
        links = {
            'home': {
                'key': 'home',
                'label': 'Inicio',
                'description': 'Portada interna con accesos rapidos.',
                'url': '/portal-inicio',
            },
            'help': {
                'key': 'help',
                'label': 'Ayuda',
                'description': 'Preguntas frecuentes y recorridos guiados.',
                'url': '/portal-ayuda',
            },
            'portal_gestor': self._build_menu_link(
                'portal_gestor',
                'Portal Gestor',
                'portalGestor.portalgestor_menu_root',
                'Calendario diario de asignaciones confirmadas.',
            ),
            'trabajos_fijos': self._build_menu_link(
                'trabajos_fijos',
                'Trabajos Fijos',
                'portalGestor.portalgestor_menu_asignacion_mensual',
                'Plantillas mensuales y tramos repetitivos.',
            ),
            'aps': self._build_menu_link(
                'aps',
                'APs',
                'trabajadores.menu_1_list',
                'Catalogo de APs y mantenimiento de sus fichas.',
            ),
            'usuarios': self._build_menu_link(
                'usuarios',
                'Usuarios',
                'usuarios.menu_1_list',
                'Altas, edicion y servicios de usuarios.',
            ),
            'consultar_horario': self._build_menu_link(
                'consultar_horario',
                'Consultar horario',
                'portal_ap.menu_manager_schedule_root',
                'Busqueda rapida del calendario mensual de un AP.',
            ),
        }
        return links

    def _get_home_slides(self, link_map):
        portal_link = link_map.get('portal_gestor') or link_map['help']
        fixed_link = link_map.get('trabajos_fijos') or link_map.get('aps') or link_map['help']
        aps_link = link_map.get('aps') or link_map['help']
        users_link = link_map.get('usuarios') or link_map['help']
        schedule_link = link_map.get('consultar_horario') or aps_link or link_map['help']
        help_link = link_map['help']
        slides = [
            {
                'badge': 'Portal interno',
                'title': 'Organiza el trabajo diario desde un solo punto',
                'description': (
                    'Entra a Portal Gestor para revisar asignaciones confirmadas, abrir el '
                    'calendario y preparar el reparto diario.'
                ),
                'cta_label': portal_link['label'],
                'cta_url': portal_link['url'],
                'class_name': 'o_portal_internal_carousel_item--primary',
            },
            {
                'badge': 'Planificacion',
                'title': 'Mantiene los trabajos fijos al dia',
                'description': (
                    'Gestiona plantillas mensuales, replica semanas completas y ajusta cada dia '
                    'sin salir del flujo de planificacion.'
                ),
                'cta_label': fixed_link['label'],
                'cta_url': fixed_link['url'],
                'class_name': 'o_portal_internal_carousel_item--accent',
            },
            {
                'badge': 'Ayuda guiada',
                'title': 'Si no sabes como hacer algo, ve a la pestana Ayuda',
                'description': (
                    'Tienes respuestas rapidas para horarios, APs y usuarios sin salir del portal. '
                    'Abre Ayuda y consulta el paso a paso cuando te atasques.'
                ),
                'cta_label': 'Abrir ayuda',
                'cta_url': help_link['url'],
                'class_name': 'o_portal_internal_carousel_item--secondary',
            },
            {
                'badge': 'Equipo',
                'title': 'Consulta APs y usuarios sin perder el ritmo del dia',
                'description': (
                    'Salta rapido al mantenimiento de APs o Usuarios para revisar fichas, servicios '
                    'y cambios urgentes sin romper tu flujo de trabajo.'
                ),
                'cta_label': aps_link['label'],
                'cta_url': aps_link['url'],
                'class_name': 'o_portal_internal_carousel_item--tertiary',
            },
            {
                'badge': 'Seguimiento',
                'title': 'Ten a mano los accesos para revisar horarios al momento',
                'description': (
                    'Cuando necesites confirmar un calendario o comprobar el mes de un AP, entra '
                    'desde este portal y llega al apartado correcto en pocos clics.'
                ),
                'cta_label': schedule_link['label'],
                'cta_url': schedule_link['url'],
                'class_name': 'o_portal_internal_carousel_item--quaternary',
            },
        ]
        for index, slide in enumerate(slides):
            slide['index'] = index
            slide['is_active'] = index == 0
            if slide['cta_url'] == aps_link['url'] and aps_link['key'] == 'help':
                slide['cta_label'] = users_link['label']
                slide['cta_url'] = users_link['url']
        return slides

    def _get_help_categories(self, selected_key):
        categories = []
        for category in PORTAL_HELP_CATEGORIES:
            category_data = deepcopy(category)
            category_data['url'] = '/portal-ayuda?category=%s' % category['key']
            category_data['is_active'] = category['key'] == selected_key
            category_data['item_count'] = len(category['items'])
            for index, item in enumerate(category_data['items'], start=1):
                item['collapse_id'] = 'portal_help_%s_%s' % (category['key'], index)
                item['is_open'] = index == 1
            categories.append(category_data)
        return categories

    def _get_selected_help_key(self, requested_key):
        available_keys = {category['key'] for category in PORTAL_HELP_CATEGORIES}
        if requested_key in available_keys:
            return requested_key
        return PORTAL_HELP_CATEGORIES[0]['key']

    def _get_portal_context(self, active_page, selected_help_key=None):
        link_map = self._get_link_map()
        side_nav_links = []
        for key in (
            'home',
            'portal_gestor',
            'trabajos_fijos',
            'aps',
            'usuarios',
            'consultar_horario',
            'help',
        ):
            link = link_map.get(key)
            if not link:
                continue
            link_data = deepcopy(link)
            link_data['is_active'] = active_page == key
            side_nav_links.append(link_data)

        quick_access_links = []
        for key in ('portal_gestor', 'aps', 'usuarios', 'help'):
            link = link_map.get(key)
            if link:
                quick_access_links.append(deepcopy(link))

        selected_key = self._get_selected_help_key(selected_help_key)
        help_categories = self._get_help_categories(selected_key)
        selected_help = next(
            category for category in help_categories if category['key'] == selected_key
        )

        return {
            'page_title': 'Portal interno',
            'user_display_name': request.env.user.name,
            'side_nav_links': side_nav_links,
            'quick_access_links': quick_access_links,
            'home_slides': self._get_home_slides(link_map),
            'help_categories': help_categories,
            'selected_help': selected_help,
            'selected_help_key': selected_key,
        }

    @http.route(['/portal-inicio'], type='http', auth='user', methods=['GET'], sitemap=False)
    def portal_inicio(self, **kwargs):
        values = self._get_portal_context(active_page='home')
        values.update({
            'page_title': 'Portal interno',
        })
        return request.render('portalGestor.portal_internal_home', values)

    @http.route(['/portal-ayuda'], type='http', auth='user', methods=['GET'], sitemap=False)
    def portal_ayuda(self, category=None, **kwargs):
        values = self._get_portal_context(active_page='help', selected_help_key=category)
        values.update({
            'page_title': 'Centro de ayuda',
        })
        return request.render('portalGestor.portal_internal_help', values)
