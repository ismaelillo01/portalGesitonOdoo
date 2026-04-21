# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


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
    _order = 'name, apellido1, apellido2, id'

    _HOGAR_RIESGO_AGUSTO_SELECTION = [
        ('hr1', 'HR1'),
        ('hr2', 'HR2'),
        ('hr3', 'HR3'),
        ('hr4', 'HR4'),
    ]
    _HOGAR_RIESGO_INTECUM_SELECTION = [
        ('hs', 'HS'),
        ('hrb', 'HRB'),
        ('hri', 'HRI'),
    ]
    _HOGAR_RIESGO_GROUP_MAP = {
        'agusto': {value for value, _label in _HOGAR_RIESGO_AGUSTO_SELECTION},
        'intecum': {value for value, _label in _HOGAR_RIESGO_INTECUM_SELECTION},
    }
    _HOGAR_RIESGO_SELECTION = _HOGAR_RIESGO_AGUSTO_SELECTION + _HOGAR_RIESGO_INTECUM_SELECTION

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
    hogar_riesgo = fields.Selection(
        _HOGAR_RIESGO_SELECTION,
        string='Hogar de Riesgo',
        index=True,
    )
    hogar_riesgo_agusto = fields.Selection(
        _HOGAR_RIESGO_AGUSTO_SELECTION,
        string='Hogar de Riesgo Agusto',
        compute='_compute_hogar_riesgo_variants',
        inverse='_inverse_hogar_riesgo_agusto',
    )
    hogar_riesgo_intecum = fields.Selection(
        _HOGAR_RIESGO_INTECUM_SELECTION,
        string='Hogar de Riesgo Intecum',
        compute='_compute_hogar_riesgo_variants',
        inverse='_inverse_hogar_riesgo_intecum',
    )

    zona_trabajo_id = fields.Many2one(
        'zonastrabajo.zona',
        string='Zona de Trabajo',
        required=True,
        ondelete='restrict',
        index=True,
    )
    gestor_id = fields.Many2one(
        'gestores.gestor',
        string='Gestor',
        ondelete='set null',
        index=True,
        copy=False,
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

    def _is_portalgestor_user_selector_context(self):
        return bool(self.env.context.get('portalgestor_user_selector'))

    def _sort_for_portalgestor_user_selector(self, records, viewer=None):
        if not records:
            return records

        viewer = viewer or self._get_security_viewer()
        priority_gestor_id = viewer._get_linked_gestor_id_for_user_priority()
        safe_names = records._get_safe_display_name_map(viewer)
        gestor_rows = self.sudo().browse(records.ids).read(['gestor_id'])
        gestor_by_user_id = {
            row['id']: row['gestor_id'][0] if row.get('gestor_id') else False
            for row in gestor_rows
        }
        ordered_records = records.sorted(
            key=lambda record: (
                0 if priority_gestor_id and gestor_by_user_id.get(record.id) == priority_gestor_id else 1,
                (safe_names.get(record.id, record._get_full_name()) or '').casefold(),
                record.id,
            )
        )
        return self.browse(ordered_records.ids)

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

    @api.depends('hogar_riesgo')
    def _compute_hogar_riesgo_variants(self):
        for record in self:
            record.hogar_riesgo_agusto = (
                record.hogar_riesgo if record.hogar_riesgo in record._HOGAR_RIESGO_GROUP_MAP['agusto'] else False
            )
            record.hogar_riesgo_intecum = (
                record.hogar_riesgo if record.hogar_riesgo in record._HOGAR_RIESGO_GROUP_MAP['intecum'] else False
            )

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

    def _inverse_hogar_riesgo_agusto(self):
        for record in self:
            record.hogar_riesgo = record.hogar_riesgo_agusto or False

    def _inverse_hogar_riesgo_intecum(self):
        for record in self:
            record.hogar_riesgo = record.hogar_riesgo_intecum or False

    @api.onchange('grupo')
    def _onchange_grupo_hogar_riesgo(self):
        for record in self:
            if record.hogar_riesgo and not record._is_valid_hogar_riesgo_for_group(record.grupo, record.hogar_riesgo):
                record.hogar_riesgo = False

    def name_get(self):
        safe_names = self._get_safe_display_name_map()
        return [(record.id, safe_names.get(record.id, record._get_full_name())) for record in self]

    @api.constrains('gestor_id')
    def _check_gestor_not_admin(self):
        for record in self:
            if record.gestor_id and record.gestor_id.grupo == 'administrador':
                raise AccessError(_("No se puede relacionar un usuario con un gestor administrador."))

    @api.constrains('grupo', 'hogar_riesgo')
    def _check_hogar_riesgo_matches_group(self):
        for record in self:
            if record.hogar_riesgo and not record._is_valid_hogar_riesgo_for_group(record.grupo, record.hogar_riesgo):
                raise ValidationError(
                    _(
                        "El Hogar de Riesgo seleccionado no es valido para el grupo %(group)s."
                    ) % {'group': record._get_group_ui_data(record.grupo).get('label', record.grupo)}
                )

    def read(self, fields=None, load='_classic_read'):
        values_list = super().read(fields=fields, load=load)
        return self._mask_read_results_for_viewer(values_list)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not self._is_portalgestor_user_selector_context():
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        results = super().name_search(name=name, args=args, operator=operator, limit=None)
        if not results:
            return results

        label_by_id = dict(results)
        ordered_records = self._sort_for_portalgestor_user_selector(
            self.browse([record_id for record_id, __label in results]).exists()
        )
        if limit:
            ordered_records = ordered_records[:limit]
        return [(record.id, label_by_id.get(record.id, record.display_name)) for record in ordered_records]

    @api.model
    @api.readonly
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        if not self._is_portalgestor_user_selector_context():
            return super().web_search_read(
                domain,
                specification,
                offset=offset,
                limit=limit,
                order=order,
                count_limit=count_limit,
            )

        fields_to_fetch = {
            'name',
            'apellido1',
            'apellido2',
            'gestor_id',
            'grupo',
        }
        fields_to_fetch.update(
            field_name
            for field_name in specification.keys()
            if field_name in self._fields and field_name != 'display_name'
        )
        records = self.search_fetch(domain, fields_to_fetch, order=order or self._order)
        records = self._sort_for_portalgestor_user_selector(records)
        total_length = len(records)
        if offset:
            records = records[offset:]
        if limit is not None:
            records = records[:limit]
        values_records = records.web_read(specification)
        return {
            'length': total_length,
            'records': values_records,
        }

    @api.model
    def _get_group_ui_data(self, grupo):
        return dict(self._GROUP_UI_DATA.get(grupo, {'badge': '', 'label': ''}))

    @api.model
    def _is_valid_hogar_riesgo_for_group(self, grupo, hogar_riesgo):
        if not hogar_riesgo:
            return True
        return hogar_riesgo in self._HOGAR_RIESGO_GROUP_MAP.get(grupo, set())

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
