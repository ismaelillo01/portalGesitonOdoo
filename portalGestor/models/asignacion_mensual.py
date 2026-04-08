# -*- coding: utf-8 -*-
import json
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import create_index


class AsignacionMensual(models.Model):
    _name = 'portalgestor.asignacion.mensual'
    _description = 'Trabajo Fijo'
    _order = 'fecha_inicio desc, usuario_id, id desc'

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    usuario_id = fields.Many2one(
        'usuarios.usuario',
        string='Usuario',
        required=True,
        ondelete='cascade',
        index=True,
    )
    usuario_grupo = fields.Selection(
        related='usuario_id.grupo',
        string='Grupo del Usuario',
        store=True,
        readonly=True,
        index=True,
    )
    usuario_localidad_id = fields.Many2one(
        related='usuario_id.localidad_id',
        string='Localidad del Usuario',
        readonly=True,
    )
    usuario_zona_trabajo_id = fields.Many2one(
        'zonastrabajo.zona',
        related='usuario_id.zona_trabajo_id',
        string='Zona del Usuario',
        store=True,
        readonly=True,
        index=True,
    )
    fecha_inicio = fields.Date(
        string='Dia inicio',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    fecha_fin = fields.Date(
        string='Dia fin',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    linea_fija_ids = fields.One2many(
        'portalgestor.asignacion.mensual.linea',
        'asignacion_mensual_id',
        string='Tramos fijos',
        copy=True,
    )
    asignacion_linea_ids = fields.One2many(
        'portalgestor.asignacion.linea',
        'asignacion_mensual_id',
        string='Asignaciones generadas',
    )
    confirmado = fields.Boolean(string='Horario Confirmado', default=False)
    gestor_owner_id = fields.Many2one(
        'res.users',
        string='Gestor propietario',
        default=lambda self: self.env.user,
        ondelete='set null',
        index=True,
        copy=False,
    )
    gestor_owner_label = fields.Char(
        string='Gestor propietario',
        compute='_compute_gestor_owner_label',
    )
    edit_session_pending = fields.Boolean(string='Edicion pendiente', default=False, copy=False)
    edit_snapshot_data = fields.Text(string='Snapshot de edicion', copy=False)
    excepcion_ids = fields.One2many(
        'portalgestor.asignacion.mensual.excepcion',
        'asignacion_mensual_id',
        string='Excepciones por dia',
    )
    total_dias_generados = fields.Integer(
        string='Dias generados',
        compute='_compute_generation_totals',
    )
    total_lineas_generadas = fields.Integer(
        string='Lineas generadas',
        compute='_compute_generation_totals',
    )
    manager_edit_blocked = fields.Boolean(
        string='Edicion bloqueada para el gestor actual',
        compute='_compute_manager_edit_blocked',
    )

    def init(self):
        super().init()
        create_index(
            self.env.cr,
            indexname='portalgestor_asig_mensual_owner_fecha_idx',
            tablename=self._table,
            expressions=['gestor_owner_id', 'fecha_inicio desc', 'id desc'],
        )
        self.env.cr.execute(
            f"""
                UPDATE {self._table}
                   SET gestor_owner_id = COALESCE(write_uid, create_uid)
                 WHERE gestor_owner_id IS NULL
            """
        )

    @api.depends('usuario_id.name', 'fecha_inicio', 'fecha_fin', 'linea_fija_ids')
    def _compute_name(self):
        for record in self:
            if not record.usuario_id or not record.fecha_inicio or not record.fecha_fin:
                record.name = _('Nuevo Trabajo Fijo')
                continue

            record.name = _(
                '%(usuario)s | %(fecha_inicio)s -> %(fecha_fin)s (%(tramos)s tramos)'
            ) % {
                'usuario': record.usuario_id.name,
                'fecha_inicio': fields.Date.to_string(record.fecha_inicio),
                'fecha_fin': fields.Date.to_string(record.fecha_fin),
                'tramos': len(record.linea_fija_ids),
            }

    @api.depends('usuario_grupo')
    def _compute_manager_edit_blocked(self):
        for record in self:
            record.manager_edit_blocked = not self.env.user._can_manage_target_group(record.usuario_grupo)

    @api.depends('gestor_owner_id')
    def _compute_gestor_owner_label(self):
        for record in self:
            record.gestor_owner_label = (
                record.gestor_owner_id.display_name
                or record.gestor_owner_id.name
                or _('Sin gestor')
            )

    def _ensure_current_user_can_manage_users(self, users):
        forbidden_users = users.filtered(
            lambda usuario: not self.env.user._can_manage_target_group(usuario.grupo)
        )
        if forbidden_users:
            raise AccessError(
                _("Los gestores Agusto no pueden crear, modificar ni eliminar horarios de usuarios de Intecum.")
            )

    @api.constrains('usuario_id')
    def _check_usuario_has_ap_service(self):
        for record in self:
            if record.usuario_id and not record.usuario_id.has_ap_service:
                raise ValidationError(_("Solo puedes asignar trabajos fijos a usuarios con el servicio AP activo."))

    @api.depends('asignacion_linea_ids', 'asignacion_linea_ids.fecha')
    def _compute_generation_totals(self):
        for record in self:
            fechas = {fecha for fecha in record.asignacion_linea_ids.mapped('fecha') if fecha}
            record.total_dias_generados = len(fechas)
            record.total_lineas_generadas = len(record.asignacion_linea_ids)

    @api.constrains('fecha_inicio', 'fecha_fin')
    def _check_date_range(self):
        for record in self:
            if record.fecha_inicio and record.fecha_fin and record.fecha_inicio > record.fecha_fin:
                raise ValidationError(_("El dia inicio debe ser menor o igual al dia fin."))

    @api.constrains('linea_fija_ids')
    def _check_lineas_fijas(self):
        for record in self:
            if not record.linea_fija_ids:
                raise ValidationError(_("Debes anadir al menos un tramo fijo."))

    def _get_target_dates(self):
        self.ensure_one()
        if not self.fecha_inicio or not self.fecha_fin:
            return []

        target_dates = []
        current_date = fields.Date.to_date(self.fecha_inicio)
        end_date = fields.Date.to_date(self.fecha_fin)
        while current_date <= end_date:
            target_dates.append(current_date)
            current_date += timedelta(days=1)
        return target_dates

    def _get_edit_snapshot_payload(self):
        self.ensure_one()
        return {
            'confirmado': bool(self.confirmado),
            'usuario_id': self.usuario_id.id or False,
            'fecha_inicio': fields.Date.to_string(self.fecha_inicio) if self.fecha_inicio else False,
            'fecha_fin': fields.Date.to_string(self.fecha_fin) if self.fecha_fin else False,
            'lineas': [
                {
                    'hora_inicio': linea.hora_inicio,
                    'hora_fin': linea.hora_fin,
                    'trabajador_id': linea.trabajador_id.id,
                }
                for linea in self.linea_fija_ids.sorted(key=lambda linea: (linea.hora_inicio, linea.hora_fin, linea.id))
            ],
        }

    def _set_edit_snapshot(self):
        for record in self:
            if record.edit_session_pending:
                continue
            record.write({
                'edit_session_pending': True,
                'edit_snapshot_data': json.dumps(record._get_edit_snapshot_payload()),
            })

    def _clear_edit_snapshot(self):
        if not self:
            return
        self.write({
            'edit_session_pending': False,
            'edit_snapshot_data': False,
        })

    def _restore_edit_snapshot(self):
        FixedLine = self.env['portalgestor.asignacion.mensual.linea']
        for record in self.exists().filtered(lambda monthly: monthly.edit_session_pending and monthly.edit_snapshot_data):
            snapshot = json.loads(record.edit_snapshot_data)
            restore_context = dict(
                self.env.context,
                portalgestor_skip_fixed_sync=True,
                portalgestor_skip_fixed_draft_cleanup=True,
            )
            record.linea_fija_ids.with_context(**restore_context).unlink()
            record.with_context(**restore_context).write({
                'usuario_id': snapshot.get('usuario_id') or False,
                'fecha_inicio': fields.Date.to_date(snapshot.get('fecha_inicio')),
                'fecha_fin': fields.Date.to_date(snapshot.get('fecha_fin')),
                'confirmado': bool(snapshot.get('confirmado', True)),
                'edit_session_pending': False,
                'edit_snapshot_data': False,
            })
            if snapshot.get('lineas'):
                FixedLine.with_context(**restore_context).create([
                    {
                        'asignacion_mensual_id': record.id,
                        'hora_inicio': line_data['hora_inicio'],
                        'hora_fin': line_data['hora_fin'],
                        'trabajador_id': line_data['trabajador_id'],
                    }
                    for line_data in snapshot['lineas']
                ])
            record.with_context(portalgestor_skip_fixed_draft_cleanup=True)._sync_generated_assignments()
            if snapshot.get('confirmado', True):
                record.asignacion_linea_ids.mapped('asignacion_id').write({'confirmado': True})
                record.write({'confirmado': True})
        return True

    def action_descartar_edicion(self):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        self._restore_edit_snapshot()
        return True

    def _apply_confirmation_as_current_manager(self):
        if not self:
            return True
        generated_assignments = self.asignacion_linea_ids.mapped('asignacion_id').exists()
        if generated_assignments:
            generated_assignments.write({'gestor_owner_id': self.env.user.id})
        self.write({
            'confirmado': True,
            'edit_session_pending': False,
            'edit_snapshot_data': False,
            'gestor_owner_id': self.env.user.id,
        })
        return True

    def action_eliminar_borrador_no_verificado(self):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        if not self.confirmado and not self.edit_session_pending:
            self.unlink()
        return True

    def _mark_unconfirmed(self):
        if not self:
            return
        self.env.cr.execute(
            """
                UPDATE portalgestor_asignacion_mensual
                   SET confirmado = FALSE
                 WHERE id IN %s
                   AND confirmado = TRUE
            """,
            [tuple(self.ids)],
        )
        self.invalidate_recordset(['confirmado'])

    def _get_manual_exception_dates(self, target_dates):
        self.ensure_one()
        if not target_dates:
            return set()

        exceptions = self.env['portalgestor.asignacion.mensual.excepcion'].search([
            ('asignacion_mensual_id', '=', self.id),
            ('fecha', 'in', target_dates),
        ])
        return {
            fields.Date.to_string(exception.fecha)
            for exception in exceptions
            if exception.fecha
        }

    def _cleanup_invalid_drafts(self):
        if self.env.context.get('portalgestor_skip_fixed_draft_cleanup'):
            return self.browse()
        records_to_remove = self.exists().filtered(
            lambda record: not record.confirmado
            and not record.edit_session_pending
            and (not record.asignacion_linea_ids or not record.total_dias_generados or not record.total_lineas_generadas)
        )
        if records_to_remove:
            records_to_remove.with_context(portalgestor_skip_fixed_sync=True).unlink()
        return records_to_remove

    def _sync_generated_assignments(self):
        Assignment = self.env['portalgestor.asignacion']
        AssignmentLine = self.env['portalgestor.asignacion.linea']

        for record in self:
            target_dates = record._get_target_dates()
            target_dates_by_key = {
                fields.Date.to_string(target_date): target_date
                for target_date in target_dates
            }
            fixed_lines = record.linea_fija_ids.sorted(
                key=lambda line: (line.hora_inicio, line.hora_fin, line.id)
            )
            today = fields.Date.to_date(fields.Date.context_today(record))
            manual_exception_dates = record._get_manual_exception_dates(target_dates)
            target_keys = set()
            active_dates = set()
            for date_key, target_date in target_dates_by_key.items():
                if record.usuario_id.baja and target_date >= today:
                    continue
                if date_key in manual_exception_dates:
                    continue

                for fixed_line in fixed_lines:
                    if fixed_line.trabajador_id.baja and target_date >= today:
                        continue
                    target_keys.add((date_key, fixed_line.id))
                    active_dates.add(date_key)

            existing_lines_by_key = {}
            lines_to_remove = AssignmentLine.browse()
            touched_assignments = record.asignacion_linea_ids.mapped('asignacion_id')

            for line in record.asignacion_linea_ids.sorted(
                key=lambda line: (line.fecha, line.hora_inicio, line.hora_fin, line.id)
            ):
                line_key = (
                    fields.Date.to_string(line.fecha),
                    line.asignacion_mensual_linea_id.id,
                )
                if not line_key[1] or line_key not in target_keys or line_key in existing_lines_by_key:
                    lines_to_remove |= line
                    continue
                existing_lines_by_key[line_key] = line

            if lines_to_remove:
                touched_assignments |= lines_to_remove.mapped('asignacion_id')
                lines_to_remove.with_context(
                    portalgestor_skip_fixed_sync=True,
                    portalgestor_skip_fixed_exception=True,
                ).unlink()

            assignments_by_date = {}
            if active_dates:
                assignments_by_date = {
                    fields.Date.to_string(assignment.fecha): assignment
                    for assignment in Assignment.search(
                        [
                            ('usuario_id', '=', record.usuario_id.id),
                            ('fecha', 'in', [
                                target_dates_by_key[date_key]
                                for date_key in sorted(active_dates)
                            ]),
                        ]
                    )
                }

            for date_key, target_date in target_dates_by_key.items():
                if date_key not in active_dates:
                    continue
                assignment = assignments_by_date.get(date_key)
                if not assignment:
                    assignment = Assignment.create({
                        'usuario_id': record.usuario_id.id,
                        'fecha': target_date,
                    })
                    assignments_by_date[date_key] = assignment

                touched_assignments |= assignment
                for fixed_line in fixed_lines:
                    line_key = (date_key, fixed_line.id)
                    if line_key not in target_keys:
                        continue
                    line_vals = fixed_line._get_generated_line_vals(assignment)
                    existing_line = existing_lines_by_key.get(line_key)
                    if existing_line:
                        touched_assignments |= existing_line.asignacion_id
                        if (
                            existing_line.asignacion_id != assignment
                            or existing_line.hora_inicio != fixed_line.hora_inicio
                            or existing_line.hora_fin != fixed_line.hora_fin
                            or existing_line.trabajador_id != fixed_line.trabajador_id
                            or existing_line.asignacion_mensual_id != record
                            or existing_line.asignacion_mensual_linea_id != fixed_line
                        ):
                            existing_line.with_context(
                                portalgestor_skip_fixed_sync=True,
                                portalgestor_skip_fixed_exception=True,
                            ).write(line_vals)
                            touched_assignments |= existing_line.asignacion_id
                    else:
                        matching_manual_line = assignment.lineas_ids.filtered(
                            lambda line: not line.asignacion_mensual_linea_id
                            and line.hora_inicio == fixed_line.hora_inicio
                            and line.hora_fin == fixed_line.hora_fin
                            and line.trabajador_id == fixed_line.trabajador_id
                        )[:1]
                        if matching_manual_line:
                            matching_manual_line.with_context(
                                portalgestor_skip_fixed_sync=True,
                                portalgestor_skip_fixed_exception=True,
                            ).write({
                                'asignacion_mensual_id': record.id,
                                'asignacion_mensual_linea_id': fixed_line.id,
                            })
                            generated_line = matching_manual_line
                        else:
                            generated_line = AssignmentLine.with_context(
                                portalgestor_skip_fixed_sync=True,
                                portalgestor_skip_fixed_exception=True,
                            ).create(line_vals)
                        touched_assignments |= generated_line.asignacion_id

            if touched_assignments:
                touched_assignments.cleanup_empty_assignments()
                touched_assignments.exists().write({'confirmado': False})
                record._mark_unconfirmed()
        self._cleanup_invalid_drafts()

    @api.model_create_multi
    def create(self, vals_list):
        usuario_ids = [vals.get('usuario_id') for vals in vals_list if vals.get('usuario_id')]
        if usuario_ids:
            self._ensure_current_user_can_manage_users(
                self.env['usuarios.usuario'].browse(usuario_ids).exists()
            )
        vals_list = [dict(vals, confirmado=vals.get('confirmado', False)) for vals in vals_list]
        records = super(
            AsignacionMensual,
            self.with_context(portalgestor_skip_fixed_sync=True),
        ).create(vals_list)
        records._sync_generated_assignments()
        return records

    def write(self, vals):
        target_users = self.mapped('usuario_id')
        if vals.get('usuario_id'):
            target_users |= self.env['usuarios.usuario'].browse(vals['usuario_id']).exists()
        self._ensure_current_user_can_manage_users(target_users)
        if vals.get('confirmado') is True:
            vals = dict(vals, edit_session_pending=False, edit_snapshot_data=False)
        if set(vals).issubset({'confirmado', 'edit_session_pending', 'edit_snapshot_data', 'gestor_owner_id'}):
            return super(
                AsignacionMensual,
                self.with_context(portalgestor_skip_fixed_sync=True),
            ).write(vals)
        if 'confirmado' not in vals:
            vals = dict(vals, confirmado=False)
        result = super(
            AsignacionMensual,
            self.with_context(portalgestor_skip_fixed_sync=True),
        ).write(vals)
        self._sync_generated_assignments()
        return result

    def action_verificar_y_confirmar(self):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        if not self.env.context.get('portalgestor_skip_fixed_sync_before_verify'):
            self._sync_generated_assignments()
        asignaciones_pendientes = self.asignacion_linea_ids.mapped('asignacion_id').exists().sorted(
            key=lambda asignacion: (asignacion.fecha, asignacion.id)
        ).filtered(lambda asignacion: not asignacion.confirmado)

        batch_conflicts = self._collect_batch_overlap_conflicts(asignaciones_pendientes)
        if batch_conflicts['protected']:
            return self._launch_batch_conflict_wizard(
                'protected_intecum_overlapping_batch',
                batch_conflicts['protected'],
                batch_conflicts['protected_summary'],
            )
        if batch_conflicts['overlapping']:
            return self._launch_batch_conflict_wizard(
                'overlapping_batch',
                batch_conflicts['overlapping'],
                batch_conflicts['overlap_summary'],
            )

        for asignacion in asignaciones_pendientes:
            result = asignacion._get_verification_action(asignacion_mensual_id=self.id)
            if isinstance(result, dict):
                return result
            asignacion._apply_confirmation_as_current_manager()

        return self._apply_confirmation_as_current_manager()

    def _get_pending_generated_lines_for_assignment(self, assignment):
        self.ensure_one()
        return assignment.lineas_ids.filtered(
            lambda line: line.asignacion_mensual_id.id == self.id and line.trabajador_id
        ).sorted(key=lambda line: (line.hora_inicio, line.hora_fin, line.id))

    def _run_fixed_assignment_target_checks(self, assignment):
        self.ensure_one()
        if assignment.usuario_id.baja:
            raise ValidationError(_("No puedes confirmar un horario para un usuario dado de baja."))
        if not assignment.usuario_id.has_ap_service:
            raise ValidationError(_("Solo puedes confirmar horarios para usuarios con el servicio AP activo."))

        target_lines = self._get_pending_generated_lines_for_assignment(assignment)
        if not target_lines:
            return target_lines

        vacaciones = self.env['trabajadores.vacacion'].search([
            ('trabajador_id', 'in', target_lines.mapped('trabajador_id').ids),
            ('date_start', '<=', assignment.fecha),
            ('date_stop', '>=', assignment.fecha),
        ])
        vacaciones_por_trabajador = {vacacion.trabajador_id.id: vacacion for vacacion in vacaciones}
        target_zone = assignment.usuario_id.zona_trabajo_id
        lineas_por_trabajador = {}

        for line in target_lines:
            trabajador = line.trabajador_id
            lineas_por_trabajador.setdefault(trabajador.id, []).append(line)
            if trabajador.baja:
                raise ValidationError(
                    _("El AP %(worker)s esta dado de baja y no se puede confirmar en %(date)s.")
                    % {
                        'worker': trabajador.display_name or trabajador.name,
                        'date': fields.Date.to_string(assignment.fecha),
                    }
                )
            if target_zone and target_zone not in trabajador.zona_trabajo_ids:
                raise ValidationError(
                    _("El AP %(worker)s no pertenece a la zona %(zone)s del usuario.")
                    % {
                        'worker': trabajador.display_name or trabajador.name,
                        'zone': target_zone.display_name or target_zone.name,
                    }
                )
            vacacion = vacaciones_por_trabajador.get(trabajador.id)
            if vacacion:
                raise ValidationError(
                    _("El AP %(worker)s tiene vacaciones el dia %(date)s y no se puede confirmar este horario.")
                    % {
                        'worker': trabajador.display_name or trabajador.name,
                        'date': fields.Date.to_string(assignment.fecha),
                    }
                )

        for worker_lines in lineas_por_trabajador.values():
            previous_line = False
            for line in sorted(worker_lines, key=lambda item: (item.hora_inicio, item.hora_fin, item.id)):
                if previous_line and line.hora_inicio < previous_line.hora_fin:
                    trabajador = line.trabajador_id or previous_line.trabajador_id
                    raise ValidationError(
                        _("El AP %(worker)s tiene dos tramos solapados dentro del mismo horario.")
                        % {
                            'worker': trabajador.display_name or trabajador.name,
                        }
                    )
                previous_line = line

        return target_lines

    def _collect_batch_overlap_conflicts(self, assignments):
        protected_ids = set()
        overlap_ids = set()
        protected_summary = []
        overlap_summary = []
        seen_conflict_ids = set()
        viewer = self.env.user

        for asignacion in assignments:
            target_lines = self._run_fixed_assignment_target_checks(asignacion)
            if not target_lines:
                continue

            current_line_ids = set(target_lines.ids)
            otras_lineas = self.env['portalgestor.asignacion.linea'].search(
                [
                    ('trabajador_id', 'in', target_lines.mapped('trabajador_id').ids),
                    ('fecha', '=', asignacion.fecha),
                ],
                order='asignacion_id, trabajador_id, hora_inicio, hora_fin, id',
            ).filtered(
                lambda line: line.id not in current_line_ids and line.trabajador_id
            )
            user_view_data = self.env['usuarios.usuario'].get_portalgestor_user_view_data(
                otras_lineas.mapped('asignacion_id.usuario_id').ids
            )
            otras_por_trabajador = {}
            for otra_linea in otras_lineas:
                otras_por_trabajador.setdefault(otra_linea.trabajador_id.id, []).append(otra_linea)

            for linea in target_lines:
                for conflicto in otras_por_trabajador.get(linea.trabajador_id.id, []):
                    overlap = min(linea.hora_fin, conflicto.hora_fin) - max(
                        linea.hora_inicio, conflicto.hora_inicio
                    )
                    if overlap <= 0:
                        continue
                    if conflicto.id in seen_conflict_ids:
                        continue
                    seen_conflict_ids.add(conflicto.id)
                    summary_line = _(
                        "%(date)s | %(worker)s | %(start)s - %(end)s | %(user)s"
                    ) % {
                        'date': fields.Date.to_string(asignacion.fecha),
                        'worker': linea.trabajador_id.display_name or linea.trabajador_id.name,
                        'start': asignacion._format_hora(conflicto.hora_inicio),
                        'end': asignacion._format_hora(conflicto.hora_fin),
                        'user': (
                            user_view_data.get(conflicto.asignacion_id.usuario_id.id, {}).get('display_name')
                            or conflicto.asignacion_id.usuario_id.display_name
                        ),
                    }
                    if not viewer._can_manage_target_group(conflicto.asignacion_id.usuario_id.grupo):
                        protected_ids.add(conflicto.id)
                        protected_summary.append(summary_line)
                    else:
                        overlap_ids.add(conflicto.id)
                        overlap_summary.append(summary_line)

        return {
            'protected': sorted(protected_ids),
            'overlapping': sorted(overlap_ids),
            'protected_summary': "\n".join(protected_summary),
            'overlap_summary': "\n".join(overlap_summary),
        }

    def _launch_batch_conflict_wizard(self, conflict_type, conflict_line_ids, summary_text):
        wizard = self.env['portalgestor.conflict.wizard'].create({
            'asignacion_mensual_id': self.id,
            'conflict_type': conflict_type,
            'batch_conflict_line_ids': [(6, 0, conflict_line_ids)],
            'info_resumen': summary_text,
        })
        return {
            'name': 'Conflicto de Horario',
            'type': 'ir.actions.act_window',
            'res_model': 'portalgestor.conflict.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_editar(self):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        if self.confirmado and not self.edit_session_pending:
            self._set_edit_snapshot()
        self.confirmado = False
        self.asignacion_linea_ids.mapped('asignacion_id').write({'confirmado': False})
        return True

    def action_eliminar_horario(self):
        self.ensure_one()
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        self.unlink()
        return {'type': 'ir.actions.act_window_close'}

    def unlink(self):
        self._ensure_current_user_can_manage_users(self.mapped('usuario_id'))
        touched_assignments = self.mapped('asignacion_linea_ids.asignacion_id')
        generated_lines = self.mapped('asignacion_linea_ids')
        exception_keys = {
            (exception.asignacion_mensual_id.id, exception.fecha)
            for exception in self.mapped('excepcion_ids')
            if exception.asignacion_mensual_id and exception.fecha
        }
        generated_lines = generated_lines.filtered(
            lambda line: (line.asignacion_mensual_id.id, line.fecha) not in exception_keys
        )
        generated_lines.with_context(
            portalgestor_skip_fixed_sync=True,
            portalgestor_skip_fixed_exception=True,
        ).unlink()
        touched_assignments.cleanup_empty_assignments()
        return super(
            AsignacionMensual,
            self.with_context(portalgestor_skip_fixed_sync=True),
        ).unlink()

    def name_get(self):
        user_view_data = self.env['usuarios.usuario'].get_portalgestor_user_view_data(
            self.mapped('usuario_id').ids
        )
        return [
            (
                record.id,
                _('%(usuario)s | %(fecha_inicio)s -> %(fecha_fin)s (%(tramos)s tramos)') % {
                    'usuario': user_view_data.get(record.usuario_id.id, {}).get('display_name')
                    or record.usuario_id.display_name
                    or record.usuario_id.name,
                    'fecha_inicio': fields.Date.to_string(record.fecha_inicio),
                    'fecha_fin': fields.Date.to_string(record.fecha_fin),
                    'tramos': len(record.linea_fija_ids),
                },
            )
            for record in self
        ]


class AsignacionMensualLinea(models.Model):
    _name = 'portalgestor.asignacion.mensual.linea'
    _description = 'Tramo de Trabajo Fijo'
    _order = 'hora_inicio, hora_fin, id'

    asignacion_mensual_id = fields.Many2one(
        'portalgestor.asignacion.mensual',
        string='Trabajo fijo',
        required=True,
        ondelete='cascade',
        index=True,
    )
    usuario_zona_trabajo_id = fields.Many2one(
        'zonastrabajo.zona',
        related='asignacion_mensual_id.usuario_zona_trabajo_id',
        string='Zona del Usuario',
        store=True,
        readonly=True,
        index=True,
    )
    hora_inicio = fields.Float(string='Hora Inicio', required=True)
    hora_fin = fields.Float(string='Hora Fin', required=True)
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='AP',
        required=True,
        ondelete='restrict',
        index=True,
    )
    asignacion_linea_ids = fields.One2many(
        'portalgestor.asignacion.linea',
        'asignacion_mensual_linea_id',
        string='Asignaciones generadas',
    )

    def _ensure_current_user_can_manage_parent_records(self, parent_records):
        self.env['portalgestor.asignacion.mensual']._ensure_current_user_can_manage_users(
            parent_records.mapped('usuario_id')
        )

    def _get_generated_line_vals(self, assignment):
        self.ensure_one()
        return {
            'asignacion_id': assignment.id,
            'hora_inicio': self.hora_inicio,
            'hora_fin': self.hora_fin,
            'trabajador_id': self.trabajador_id.id,
            'asignacion_mensual_id': self.asignacion_mensual_id.id,
            'asignacion_mensual_linea_id': self.id,
        }

    @api.model_create_multi
    def create(self, vals_list):
        parent_ids = [vals.get('asignacion_mensual_id') for vals in vals_list if vals.get('asignacion_mensual_id')]
        if parent_ids:
            self._ensure_current_user_can_manage_parent_records(
                self.env['portalgestor.asignacion.mensual'].browse(parent_ids).exists()
            )
        records = super().create(vals_list)
        if not self.env.context.get('portalgestor_skip_fixed_sync'):
            records.mapped('asignacion_mensual_id')._sync_generated_assignments()
        return records

    def write(self, vals):
        parent_records = self.mapped('asignacion_mensual_id')
        if vals.get('asignacion_mensual_id'):
            parent_records |= self.env['portalgestor.asignacion.mensual'].browse(vals['asignacion_mensual_id']).exists()
        self._ensure_current_user_can_manage_parent_records(parent_records)
        result = super().write(vals)
        if not self.env.context.get('portalgestor_skip_fixed_sync'):
            (parent_records | self.mapped('asignacion_mensual_id')).exists()._sync_generated_assignments()
        return result

    def unlink(self):
        parent_records = self.mapped('asignacion_mensual_id')
        self._ensure_current_user_can_manage_parent_records(parent_records)
        result = super().unlink()
        if not self.env.context.get('portalgestor_skip_fixed_sync'):
            parent_records.exists()._sync_generated_assignments()
        return result

    @api.constrains('hora_inicio', 'hora_fin')
    def _check_horas(self):
        for record in self:
            if record.hora_inicio < 0 or record.hora_inicio >= 24:
                raise ValidationError(_("La hora de inicio debe estar entre 00:00 y 23:59."))
            if record.hora_fin < 0 or record.hora_fin >= 24:
                raise ValidationError(_("La hora de fin debe estar entre 00:00 y 23:59."))
            if record.hora_inicio >= record.hora_fin:
                raise ValidationError(_("La hora de inicio debe ser anterior a la hora de fin."))
