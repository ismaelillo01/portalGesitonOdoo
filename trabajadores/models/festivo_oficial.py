# -*- coding: utf-8 -*-
import csv
import html
import io
import logging
import re
from datetime import date
from urllib.error import URLError
from urllib.request import urlopen

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

JCYL_OFFICIAL_HOLIDAYS_CSV_URL = (
    'https://datosabiertos.jcyl.es/web/jcyl/risp/es/empleo/laboral-cyl/1284165791785.csv'
)
BOE_SEARCH_URL = 'https://www.boe.es/buscar/boe.php'
BOE_DOCUMENT_URL = 'https://www.boe.es/buscar/doc.php?id=%s'
BOE_CASTILLA_Y_LEON_HEADER = 'headerCastillaYL'

NATIONAL_HOLIDAY_NAMES = {
    'año nuevo',
    'ano nuevo',
    'epifanía del señor',
    'epifania del señor',
    'epifanía del senor',
    'epifania del senor',
    'jueves santo',
    'viernes santo',
    'fiesta del trabajo',
    'asunción de la virgen',
    'asuncion de la virgen',
    'fiesta nacional de españa',
    'fiesta nacional de espana',
    'todos los santos',
    'día de la constitución española',
    'dia de la constitucion española',
    'día de la constitución espana',
    'dia de la constitucion espana',
    'inmaculada concepción',
    'inmaculada concepcion',
    'natividad del señor',
    'natividad del senor',
    'san josé',
    'san jose',
    'día de santiago apóstol',
    'dia de santiago apostol',
    'santiago apóstol',
    'santiago apostol',
}


class FestivoOficial(models.Model):
    _name = 'trabajadores.festivo.oficial'
    _description = 'Festivo oficial CyL'
    _order = 'fecha desc, id desc'

    _sql_constraints = [
        (
            'trabajadores_festivo_oficial_unique_fecha',
            'unique(fecha)',
            'Ya existe un festivo oficial para esta fecha.',
        ),
    ]

    name = fields.Char(string='Nombre', required=True)
    fecha = fields.Date(string='Fecha efectiva', required=True, index=True)
    fecha_original = fields.Date(string='Fecha original')
    anio = fields.Integer(
        string='Año',
        compute='_compute_anio',
        store=True,
        index=True,
    )
    trasladado = fields.Boolean(string='Trasladado', default=False)
    source_scope = fields.Selection(
        [
            ('national', 'Nacional'),
            ('autonomic', 'Autonómico'),
        ],
        string='Ámbito interno',
        required=True,
        default='national',
    )
    source_kind = fields.Selection(
        [
            ('jcyl_csv', 'JCyL CSV'),
            ('boe_html', 'BOE HTML'),
            ('manual', 'Manual'),
        ],
        string='Fuente',
        required=True,
        default='manual',
    )
    source_reference = fields.Char(string='Referencia de origen')
    source_url = fields.Char(string='URL de origen')
    manual_override = fields.Boolean(string='Corrección manual', default=False)
    active = fields.Boolean(string='Activo', default=True)

    @api.depends('fecha')
    def _compute_anio(self):
        for record in self:
            record.anio = record.fecha.year if record.fecha else 0

    @staticmethod
    def _normalize_holiday_name(name):
        normalized = (name or '').strip().casefold()
        return ' '.join(normalized.split())

    @classmethod
    def _get_scope_from_name(cls, holiday_name):
        normalized_name = cls._normalize_holiday_name(holiday_name)
        if (
            'castilla y león' in normalized_name
            or 'castilla y leon' in normalized_name
            or 'comunidad autónoma' in normalized_name
            or 'comunidad autonoma' in normalized_name
        ):
            return 'autonomic'
        if normalized_name in NATIONAL_HOLIDAY_NAMES:
            return 'national'
        return 'national'

    @staticmethod
    def _parse_spanish_date(value):
        value = (value or '').strip()
        if not value:
            return False
        try:
            return date(
                int(value[6:10]),
                int(value[3:5]),
                int(value[0:2]),
            )
        except Exception as error:
            raise ValidationError(_("No se pudo interpretar la fecha '%s'.") % value) from error

    @classmethod
    def _decode_http_payload(cls, payload):
        for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode('utf-8', errors='ignore')

    @classmethod
    def _strip_html(cls, value):
        return re.sub(r'<[^>]+>', '', html.unescape(value or '')).strip()

    def _http_get_text(self, url):
        with urlopen(url, timeout=20) as response:
            return self._decode_http_payload(response.read())

    def _fetch_jcyl_csv_text(self):
        return self._http_get_text(JCYL_OFFICIAL_HOLIDAYS_CSV_URL)

    def _fetch_boe_search_html(self, target_year):
        query_string = (
            'campo%5B0%5D=ORIS'
            '&dato%5B0%5D%5B1%5D=1'
            '&dato%5B0%5D%5B2%5D=2'
            '&dato%5B0%5D%5B3%5D=3'
            '&dato%5B0%5D%5B4%5D=4'
            '&dato%5B0%5D%5B5%5D=5'
            '&dato%5B0%5D%5BT%5D=T'
            '&operador%5B0%5D=and'
            '&campo%5B1%5D=TITULOS'
            f'&dato%5B1%5D=fiestas+laborales+para+el+a%C3%B1o+{target_year}'
            '&operador%5B1%5D=and'
            '&sort_field%5B0%5D=FPU'
            '&sort_order%5B0%5D=desc'
            '&sort_field%5B1%5D=ORI'
            '&sort_order%5B1%5D=asc'
            '&sort_field%5B2%5D=REF'
            '&sort_order%5B2%5D=asc'
            '&accion=Buscar'
        )
        return self._http_get_text(f'{BOE_SEARCH_URL}?{query_string}')

    def _fetch_boe_doc_html(self, document_id):
        return self._http_get_text(BOE_DOCUMENT_URL % document_id)

    def _parse_jcyl_csv_rows(self, csv_text):
        rows = []
        header_found = False
        reader = csv.reader(io.StringIO(csv_text), delimiter=';')
        for raw_row in reader:
            row = [column.strip() for column in raw_row]
            if not any(row):
                continue
            if not header_found:
                if len(row) >= 4 and row[:4] == [
                    'Nombre de la fiesta',
                    'Fecha festivo',
                    'Trasladado',
                    'Fecha disfrute',
                ]:
                    header_found = True
                continue

            if len(row) < 4:
                continue

            fecha_original = self._parse_spanish_date(row[1])
            fecha_efectiva = self._parse_spanish_date(row[3]) or fecha_original
            if not fecha_efectiva:
                continue

            rows.append({
                'anio': fecha_efectiva.year,
                'name': row[0],
                'fecha': fecha_efectiva,
                'fecha_original': fecha_original,
                'trasladado': (row[2] or '').strip().casefold() in ('si', 'sí'),
                'source_scope': self._get_scope_from_name(row[0]),
                'source_kind': 'jcyl_csv',
                'source_reference': 'laboral-cyl/1284165791785.csv',
                'source_url': JCYL_OFFICIAL_HOLIDAYS_CSV_URL,
            })
        return rows

    def _extract_boe_document_id(self, html_text):
        match = re.search(r'doc\.php\?id=(BOE-A-\d{4}-\d+)', html_text or '')
        return match.group(1) if match else False

    def _parse_boe_rows(self, html_text, target_year, document_id):
        rows = []
        for row_html in re.findall(r'<tr>(.*?)</tr>', html_text or '', flags=re.DOTALL):
            date_cell = re.search(
                r'<td id="header(?P<day>\d{2})(?P<month>\d{2})[A-Z]?"[^>]*>[^<]*\d+\s+(?P<label>.*?)</td>',
                row_html,
                flags=re.DOTALL,
            )
            if not date_cell:
                continue

            castilla_cell = re.search(
                rf'<td[^>]+headers="[^"]*{BOE_CASTILLA_Y_LEON_HEADER}[^"]*"[^>]*>(?P<cell>.*?)</td>',
                row_html,
                flags=re.DOTALL,
            )
            if not castilla_cell:
                continue

            abbr_match = re.search(r'<abbr title="(?P<title>[^"]+)">', castilla_cell.group('cell'))
            if not abbr_match:
                continue

            scope = 'autonomic' if 'Comunidad Autónoma' in html.unescape(abbr_match.group('title')) else 'national'
            month = int(date_cell.group('month'))
            day = int(date_cell.group('day'))
            try:
                holiday_date = date(target_year, month, day)
            except ValueError:
                continue

            rows.append({
                'anio': target_year,
                'name': self._strip_html(date_cell.group('label')).rstrip('.'),
                'fecha': holiday_date,
                'fecha_original': False,
                'trasladado': self._strip_html(date_cell.group('label')).startswith(('Lunes siguiente', 'Día siguiente', 'Dia siguiente')),
                'source_scope': scope,
                'source_kind': 'boe_html',
                'source_reference': document_id,
                'source_url': BOE_DOCUMENT_URL % document_id,
            })
        return rows

    def _prepare_sync_vals(self, holiday_row):
        return {
            'name': holiday_row['name'],
            'fecha': holiday_row['fecha'],
            'fecha_original': holiday_row.get('fecha_original') or False,
            'trasladado': bool(holiday_row.get('trasladado')),
            'source_scope': holiday_row['source_scope'],
            'source_kind': holiday_row['source_kind'],
            'source_reference': holiday_row.get('source_reference') or False,
            'source_url': holiday_row.get('source_url') or False,
            'active': True,
        }

    def _upsert_sync_rows(self, rows):
        created_or_updated = self.browse()
        for holiday_row in rows:
            existing = self.search([('fecha', '=', holiday_row['fecha'])], limit=1)
            vals = self._prepare_sync_vals(holiday_row)
            if existing:
                if existing.manual_override:
                    continue
                existing.with_context(trabajadores_festivo_sync=True).write(vals)
                created_or_updated |= existing
                continue
            created_or_updated |= self.with_context(trabajadores_festivo_sync=True).create(vals)
        return created_or_updated

    def _sync_rows_from_jcyl_csv(self, target_year=False):
        csv_text = self._fetch_jcyl_csv_text()
        rows = self._parse_jcyl_csv_rows(csv_text)
        if target_year:
            rows = [row for row in rows if row['anio'] == target_year]
        return self._upsert_sync_rows(rows)

    def _sync_year_from_boe(self, target_year):
        search_html = self._fetch_boe_search_html(target_year)
        document_id = self._extract_boe_document_id(search_html)
        if not document_id:
            return self.browse()
        doc_html = self._fetch_boe_doc_html(document_id)
        rows = self._parse_boe_rows(doc_html, target_year, document_id)
        return self._upsert_sync_rows(rows)

    def action_sync_year(self, target_year):
        try:
            target_year = int(target_year)
        except (TypeError, ValueError) as error:
            raise ValidationError(_("Debes indicar un año válido para la sincronización.")) from error

        records = self.browse()
        try:
            records |= self._sync_rows_from_jcyl_csv(target_year=target_year)
        except Exception as error:
            _logger.warning("No se pudo sincronizar el CSV JCyL para %s: %s", target_year, error)

        if records.filtered(lambda festivo: festivo.anio == target_year):
            return records

        try:
            records |= self._sync_year_from_boe(target_year)
        except Exception as error:
            _logger.warning("No se pudo sincronizar el BOE para %s: %s", target_year, error)
        return records

    @api.model
    def cron_sync_official_holidays(self):
        current_year = fields.Date.context_today(self).year
        try:
            synced_records = self._sync_rows_from_jcyl_csv()
            csv_years = synced_records.mapped('anio') if synced_records else self.search([]).mapped('anio')
        except (ValidationError, URLError, OSError) as error:
            _logger.warning("Sincronización JCyL de festivos oficiales no disponible: %s", error)
            csv_years = self.search([]).mapped('anio')

        max_known_year = max(csv_years or [current_year - 1])
        for target_year in range(max_known_year + 1, current_year + 2):
            try:
                self._sync_year_from_boe(target_year)
            except (ValidationError, URLError, OSError) as error:
                _logger.warning("Sincronización BOE de festivos oficiales %s no disponible: %s", target_year, error)
        return True

    @api.constrains('fecha_original', 'fecha')
    def _check_original_date(self):
        for record in self:
            if record.fecha_original and record.fecha and record.fecha_original.year != record.anio:
                raise ValidationError(_("La fecha original debe pertenecer al mismo año del festivo efectivo."))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('trabajadores_festivo_sync'):
            for vals in vals_list:
                vals.setdefault('source_kind', 'manual')
                vals.setdefault('manual_override', True)
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('trabajadores_festivo_sync'):
            vals = dict(vals)
            vals.setdefault('manual_override', True)
            vals.setdefault('source_kind', 'manual')
        return super().write(vals)


class FestivoOficialSyncWizard(models.TransientModel):
    _name = 'trabajadores.festivo.oficial.sync.wizard'
    _description = 'Sincronizar festivos oficiales'

    anio = fields.Integer(
        string='Año',
        required=True,
        default=lambda self: fields.Date.context_today(self).year,
    )

    def action_sync(self):
        self.ensure_one()
        self.env['trabajadores.festivo.oficial'].action_sync_year(self.anio)
        return {'type': 'ir.actions.act_window_close'}
