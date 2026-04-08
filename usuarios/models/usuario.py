# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class UsuarioServicio(models.Model):
    _name = 'usuarios.servicio'
    _description = 'Servicio de Usuario'
    _order = 'sequence, name, id'

    name = fields.Char(string='Servicio', required=True)
    code = fields.Char(string='Codigo', required=True, index=True)
    sequence = fields.Integer(string='Secuencia', default=10)

    _sql_constraints = [
        ('usuarios_servicio_code_uniq', 'unique(code)', 'El codigo del servicio debe ser unico.'),
    ]


class Usuario(models.Model):
    _name = 'usuarios.usuario'
    _description = 'Usuario'

    _GROUP_UI_DATA = {
        'agusto': {'badge': 'A', 'label': 'Agusto'},
        'intecum': {'badge': 'I', 'label': 'Intecum'},
    }

    name = fields.Char(string='Nombre', required=True)
    apellido1 = fields.Char(string='Primer Apellido')
    apellido2 = fields.Char(string='Segundo Apellido')
    dni_nie = fields.Char(string='DNI o NIE')
    telefono = fields.Char(string='Telefono')
    direccion = fields.Char(string='Direccion')
    localidad_id = fields.Many2one(
        'zonastrabajo.localidad',
        string='Localidad',
        ondelete='restrict',
        index=True,
    )
    baja = fields.Boolean(string='Baja', default=False)
    servicio_ids = fields.Many2many(
        'usuarios.servicio',
        'usuarios_usuario_servicio_rel',
        'usuario_id',
        'servicio_id',
        string='Servicios',
    )
    has_ap_service = fields.Boolean(
        string='Servicio AP activo',
        compute='_compute_has_ap_service',
        store=True,
        index=True,
    )

    grupo = fields.Selection([
        ('intecum', 'Intecum'),
        ('agusto', 'Agusto')
    ], string='Grupo', required=True, index=True, default='agusto')

    zona_trabajo_id = fields.Many2one(
        'zonastrabajo.zona',
        string='Zona de Trabajo',
        required=True,
        ondelete='restrict',
        index=True,
    )
    manager_edit_blocked = fields.Boolean(
        string='Edicion bloqueada para el gestor actual',
        compute='_compute_manager_edit_blocked',
    )
    group_selection_locked = fields.Boolean(
        string='Grupo bloqueado para el gestor actual',
        compute='_compute_group_selection_locked',
    )

    def _get_security_viewer(self):
        viewer_uid = self.env.context.get('portalgestor_viewer_uid')
        if viewer_uid:
            viewer = self.env['res.users'].browse(viewer_uid).exists()
            if viewer:
                return viewer
        return self.env.user

    def _get_intecum_safe_sequence_map(self, user_ids):
        if not user_ids:
            return {}
        self.env.cr.execute(
            f"""
                SELECT id, seq
                  FROM (
                        SELECT id, row_number() OVER (ORDER BY id) AS seq
                          FROM {self._table}
                         WHERE grupo = 'intecum'
                       ) ranked
                 WHERE id = ANY(%s)
            """,
            [list(user_ids)],
        )
        return dict(self.env.cr.fetchall())

    def _get_safe_display_name_map(self, viewer=None):
        viewer = viewer or self._get_security_viewer()
        should_mask = viewer._should_mask_intecum_users()
        intecum_ids = self.filtered(lambda user: user.grupo == 'intecum').ids if should_mask else []
        sequence_map = self._get_intecum_safe_sequence_map(intecum_ids)
        safe_names = {}
        for record in self:
            if should_mask and record.grupo == 'intecum':
                sequence = sequence_map.get(record.id)
                safe_names[record.id] = (
                    _("Usuario Intecum %s") % sequence
                    if sequence
                    else _("Usuario Intecum")
                )
                continue
            safe_names[record.id] = record._get_full_name()
        return safe_names

    def _mask_read_results_for_viewer(self, values_list):
        viewer = self._get_security_viewer()
        if not values_list or not viewer._should_mask_intecum_users():
            return values_list

        records = self.browse([vals['id'] for vals in values_list if vals.get('id')]).exists()
        records_by_id = {record.id: record for record in records}
        safe_names = records._get_safe_display_name_map(viewer)

        for values in values_list:
            record = records_by_id.get(values.get('id'))
            if not record or record.grupo != 'intecum':
                continue

            safe_name = safe_names.get(record.id, _("Usuario Intecum"))
            if 'name' in values:
                values['name'] = safe_name
            if 'apellido1' in values:
                values['apellido1'] = ''
            if 'apellido2' in values:
                values['apellido2'] = ''
            if 'dni_nie' in values:
                values['dni_nie'] = ''
            if 'telefono' in values:
                values['telefono'] = ''
            if 'direccion' in values:
                values['direccion'] = ''
            if 'localidad_id' in values:
                values['localidad_id'] = False
            if 'display_name' in values:
                values['display_name'] = safe_name
        return values_list

    def _ensure_current_user_can_manage_target_groups(self, target_groups):
        viewer = self._get_security_viewer()
        forbidden_groups = {
            target_group
            for target_group in target_groups
            if target_group and not viewer._can_manage_target_group(target_group)
        }
        if forbidden_groups:
            raise AccessError(_("Los gestores Agusto no pueden crear, modificar ni eliminar usuarios de Intecum."))

    @api.depends('grupo')
    def _compute_manager_edit_blocked(self):
        viewer = self._get_security_viewer()
        for record in self:
            record.manager_edit_blocked = (
                record.grupo == 'intecum' and not viewer._can_manage_target_group('intecum')
            )

    @api.depends_context('uid', 'portalgestor_viewer_uid')
    def _compute_group_selection_locked(self):
        viewer = self._get_security_viewer()
        is_agusto_manager = viewer._get_gestor_management_scope() == 'agusto'
        for record in self:
            record.group_selection_locked = is_agusto_manager

    @api.depends('name', 'apellido1', 'apellido2', 'grupo')
    def _compute_display_name(self):
        safe_names = self._get_safe_display_name_map()
        for record in self:
            record.display_name = safe_names.get(record.id, '')

    @api.depends('servicio_ids.code')
    def _compute_has_ap_service(self):
        for record in self:
            record.has_ap_service = any(service.code == 'ap' for service in record.servicio_ids)

    def _get_full_name(self):
        self.ensure_one()
        parts = [part for part in [self.name, self.apellido1, self.apellido2] if part]
        return ' '.join(parts)

    def _get_service_names(self):
        self.ensure_one()
        return ', '.join(
            self.servicio_ids.sorted(key=lambda service: (service.sequence, service.name)).mapped('name')
        )

    def name_get(self):
        safe_names = self._get_safe_display_name_map()
        return [(record.id, safe_names.get(record.id, record._get_full_name())) for record in self]

    def read(self, fields=None, load='_classic_read'):
        values_list = super().read(fields=fields, load=load)
        return self._mask_read_results_for_viewer(values_list)

    @api.model
    def _get_group_ui_data(self, grupo):
        return dict(self._GROUP_UI_DATA.get(grupo, {'badge': '', 'label': ''}))

    @api.model
    def get_portalgestor_user_view_data(self, user_ids):
        users = self.browse(user_ids).exists()
        viewer = self._get_security_viewer()
        safe_names = users._get_safe_display_name_map(viewer)
        return {
            user.id: {
                'display_name': safe_names.get(user.id, user._get_full_name()),
                'masked': bool(viewer._should_mask_intecum_users() and user.grupo == 'intecum'),
                'can_edit': bool(viewer._can_manage_target_group(user.grupo)),
            }
            for user in users
        }

    @api.model
    def get_portalgestor_user_types(self, user_ids):
        users = self.browse(user_ids).exists()
        return {
            user.id: self._get_group_ui_data(user.grupo)
            for user in users
        }

    @api.model_create_multi
    def create(self, vals_list):
        self._ensure_current_user_can_manage_target_groups(vals.get('grupo') for vals in vals_list)
        return super().create(vals_list)

    def write(self, vals):
        target_groups = [vals.get('grupo', record.grupo) for record in self]
        self._ensure_current_user_can_manage_target_groups(target_groups)
        return super().write(vals)

    def unlink(self):
        self._ensure_current_user_can_manage_target_groups(self.mapped('grupo'))
        return super().unlink()
