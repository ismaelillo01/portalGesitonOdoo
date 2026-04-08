# -*- coding: utf-8 -*-
from odoo import fields, models


LOCALIDADES_RAW = """
Abarca de Campos
Abastas
Abastillas
Abia de las Torres
Acera de la Vega
Aguilar de Campoo
Alar del Rey
Alba de Cerrato
Alba de los CardaÃ±os
AlbalÃ¡ de la Vega
Amayuelas de Abajo
Amayuelas de Arriba
Amayuelas de Ojeda
Ampudia
Amusco
AntigÃ¼edad
AÃ±oza
Arbejal
Arconada
Arenillas de NuÃ±o PÃ©rez
Arenillas de San Pelayo
AreÃ±os
Arroyo
Astudillo
Autilla del Pino
Autillo de Campos
AviÃ±ante de la PeÃ±a
Ayuela
Bahillo
BaltanÃ¡s
BaÃ±os de Cerrato
BaÃ±os de la PeÃ±a
BaquerÃ­n de Campos
Barajores
BÃ¡rcena de Campos
Barcenilla de Pisuerga
Barrio de la Puebla (El)
Barrio de San Pedro
Barrio de Santa MarÃ­a
Barrios de la Vega
Barriosuso
Barruelo de SantullÃ¡n
BÃ¡scones de Ebro
BÃ¡scones de Ojeda
BÃ¡scones de Valdivia
Becerril de Campos
Becerril del Carpio
Belmonte de Campos
Berzosa de los Hidalgos
Berzosilla
Boada de Campos
Boadilla de Rioseco
Boadilla del Camino
Boedo de CastrejÃ³n
BraÃ±osera
Buenavista de Valdavia
Bustillo de la Vega
Bustillo de SantullÃ¡n
Bustillo del PÃ¡ramo de CarriÃ³n
CabaÃ±as de Castilla (Las)
Cabria
Calabazanos
Calahorra de Boedo
Calzada de los Molinos
Calzadilla de la Cueza
Camasobres
Camesa de Valdivia
Campo (El)
Camporredondo de Alba
Canduela
Cantoral de la PeÃ±a
Capillas
Carbonera
CardaÃ±o de Abajo
CardaÃ±o de Arriba
CardeÃ±osa de Volpejera
CarriÃ³n de los Condes
Casavegas
CascÃ³n de la Nava
Castil de Vela
CastrejÃ³n de la PeÃ±a
Castrillejo de la Olma
Castrillo de Don Juan
Castrillo de Onielo
Castrillo de Villavega
Castromocho
Celada de Roblecedo
Celadilla del RÃ­o
Cembrero
Cementos Hontoria
Cervatos de la Cueza
Cervera de Pisuerga
Cevico de la Torre
Cevico Navero
Cezura
Cillamayor
Cisneros
Ciudad JardÃ­n Virgen del Milagro
Cobos de Cerrato
Collazos de Boedo
Colmenares de Ojeda
Colonia Militar Infantil General Varela
Congosto de Valdavia
Cordovilla de Aguilar
Cordovilla la Real
CornÃ³n de la PeÃ±a
Cornoncillo
Corvio
Cozuelos de Ojeda
Cubillas de Cerrato
Cubillo de CastrejÃ³n
Cubillo de Ojeda
Cuillas del Valle
Dehesa de Cordovilla
Dehesa de Matanzas
Dehesa de Montejo
Dehesa de Romanos
Dehesa de San Salvador del Moral
Dehesa de Villandrando
Dehesilla
DueÃ±as
Espinosa de Cerrato
Espinosa de Villagonzalo
Esquileo de Abajo
Esquileo de Arriba
EstaciÃ³n (La)
Estalaya
Foldada
Fontecha
Frechilla
Fresno del RÃ­o
FrÃ³mista
Fuente-Andrino
Fuentes de Nava
Fuentes de Valdepero
Gama
GaÃ±inas de la Vega
GozÃ³n de Ucieza
Gramedo
Grijera
Grijota
Guardo
Guaza de Campos
Helecha de Valdivia
Heras de la PeÃ±a (Las)
HÃ©rmedes de Cerrato
Herrera de Pisuerga
Herrera de ValdecaÃ±as
Herreruela de CastillerÃ­a
Hijosa de Boedo
Hontoria de Cerrato
Hornillos de Cerrato
Husillos
Intorcisa
Itero de la Vega
Itero Seco
Lagartos
Lagunilla de la Vega
Lantadilla
Lastra (La)
Lastrilla
Lebanza
Ledigos
LigÃ¼Ã©rzana
Llazos (Los)
Lobera de la Vega
Loma de CastrejÃ³n
Lomas
Lomilla
Lores
Magaz de Pisuerga
Manquillos
Mantinos
Marcilla de Campos
Matabuena
Matalbaniega
Matamorisca
Mave
Mazariegos
Mazuecos de Valdeginate
Melgar de Yuso
Membrillar
Menaza
Meneses de Campos
Micieces de Ojeda
MiÃ±anes
Moarves de Ojeda
Monasterio
Monte la Torre
Montoto de Ojeda
MonzÃ³n de Campos
Moratinos
Moslares de la Vega
MudÃ¡
MuÃ±eca
Nava de SantullÃ¡n
Navas de Sobremonte
Naveros de Pisuerga
Nestar
Nogal de las Huertas
Nogales de Pisuerga
Nuestra SeÃ±ora de Alconada
Olea de Boedo
Olleros de Paredes Rubias
Olleros de Pisuerga
Olmillos (Los)
Olmos de Ojeda
Olmos de Pisuerga
OrbÃ³
Osornillo
Osorno
Otero de Guardo
Oteros de Boedo
Palacios del Alcor
Palencia
Palenzuela
PÃ¡ramo de Boedo
Paredes de Monte
Paredes de Nava
Payo de Ojeda
Pedraza de Campos
Pedrosa de la Vega
Perales
PerapertÃº
Perazancas de Ojeda
Piedrasluengas
Pino de Viduerna
Pino del RÃ­o
PiÃ±a de Campos
PisÃ³n de CastrejÃ³n
PisÃ³n de Ojeda
PoblaciÃ³n de Arroyo
PoblaciÃ³n de Campos
PoblaciÃ³n de Cerrato
PoblaciÃ³n de Soto
Polentinos
Polvorosa de Valdavia
Pomar de Valdivia
Porquera de los Infantes
Porquera de SantullÃ¡n
Portillejo
Poza de la Vega
Pozancos
Pozo de Urama
Pozuelos del Rey
PrÃ¡danos de Ojeda
Puebla de Valdavia (La)
Puentetoma
Quintana del Puente
QuintanadÃ­ez de la Vega
Quintanaluengos
Quintanas de Hormiguera
Quintanatello de Ojeda
Quintanilla de Corvio
Quintanilla de la Cueza
Quintanilla de las Torres
Quintanilla de OnsoÃ±a
Rabanal de los Caballeros
Rayaces
Rebanal de las Llantas
Rebolledo de la Inera
Recueva de la PeÃ±a
Reinoso de Cerrato
Relea de la Loma
Renedo de la Inera
Renedo de la Vega
Renedo de Valdavia
Renedo de Zalima
Renedo del Monte
Requena de Campos
Resoba
Respenda de Aguilar
Respenda de la PeÃ±a
Revenga de Campos
Revilla de Campos
Revilla de Collazos
Revilla de Pomar
Revilla de SantullÃ¡n
Ribas de Campos
Riberos de la Cueza
Riosmenudos de la PeÃ±a
Robladillo de Ucieza
Roscales de la PeÃ±a
Rueda de Pisuerga
Ruesga
Salcedillo
SaldaÃ±a
Salinas de Pisuerga
San AndrÃ©s de Arroyo
San AndrÃ©s de la Regla
San CebriÃ¡n de Buena Madre
San CebriÃ¡n de Campos
San CebriÃ¡n de MudÃ¡
San CristÃ³bal de Boedo
San Felices de CastillerÃ­a
San Isidro de DueÃ±as
San Juan de Redondo
San Llorente del PÃ¡ramo
San MamÃ©s de Campos
San MamÃ©s de Zalima
San MartÃ­n de los Herreros
San MartÃ­n de PerapertÃº
San MartÃ­n del Monte
San MartÃ­n del Obispo
San MartÃ­n del Valle
San NicolÃ¡s del Real Camino
San Pedro de Cansoles
San Pedro de Ojeda
San Quirce de Riopisuerga
San RomÃ¡n de la Cuba
San Salvador de Cantamuda
Santa Cecilia del Alcor
Santa Cruz de Boedo
Santa Cruz del Monte
Santa MarÃ­a de Mave
Santa MarÃ­a de Nava
Santa MarÃ­a de Redondo
Santa Olaja de la Vega
Santana
SantervÃ¡s de la Vega
Santiago del Val
SantibÃ¡Ã±ez de Ecla
SantibÃ¡Ã±ez de la PeÃ±a
SantibÃ¡Ã±ez de Resoba
SantillÃ¡n de la Vega
Santillana de Campos
Santoyo
Serna (La)
Sotillo de Boedo
Soto de Cerrato
SotobaÃ±ado y Priorato
Tabanera de Cerrato
Tabanera de Valdavia
TÃ¡mara de Campos
Tariego de Cerrato
Tarilonte de la PeÃ±a
Terradillos de los Templarios
Torquemada
Torre de los Molinos
TorremormojÃ³n
TraspeÃ±a de la PeÃ±a
Tremaya
Triollo
Vado
Valberzoso
Valbuena de Pisuerga
Valcabadillo
Valcobero
Valdebustos
ValdecaÃ±as de Cerrato
Valdegama
Valdeolmillos
ValderrÃ¡bano
Valdespina
Valenoso
Valle de Cerrato
Valle de SantullÃ¡n
Vallejo de OrbÃ³
Valles de Valdavia
Vallespinoso de Aguilar
Vallespinoso de Cervera
Valoria de Aguilar
Valoria del Alcor
ValsadornÃ­n
VaÃ±es
Vega de Bur
Vega de DoÃ±a Olimpa
Vega de Riacos
Velilla de la PeÃ±a
Velilla del RÃ­o CarriÃ³n
Velillas del Duque
Venta de BaÃ±os
Ventanilla
Ventosa de Pisuerga
Verbios
VerdeÃ±a
VergaÃ±o
Vertavillo
Vid de Ojeda (La)
Vidrieros
Viduerna de la PeÃ±a
Villabasta de Valdavia
Villabellaco
Villabermudo
Villacibio
Villacidaler
Villaconancio
Villacuende
Villada
Villadiezma
Villaeles de Valdavia
Villaescusa de Ecla
Villaescusa de las Torres
VillafrÃ­a de la PeÃ±a
Villafruel
Villafruela
VillahÃ¡n
Villaherreros
Villajimena
Villalaco
Villalafuente
Villalba de Guardo
Villalbeto de la PeÃ±a
VillalcÃ¡zar de Sirga
VillalcÃ³n
VillaldavÃ­n
Villallano
VillalobÃ³n
Villaluenga de la Vega
Villalumbroso
VillamartÃ­n de Campos
VillambrÃ¡n de Cea
Villambroz
Villamediana
Villamelendro
Villameriel
Villamorco
Villamoronta
Villamuera de la Cueza
Villamuriel de Cerrato
Villaneceriel de Boedo
Villantodrigo
Villanueva de Abajo
Villanueva de Arriba
Villanueva de Henares
Villanueva de la PeÃ±a
Villanueva de la Torre
Villanueva de los Nabos
Villanueva del Monte
Villanueva del Rebollar
Villanueva del RÃ­o
VillanuÃ±o de Valdavia
Villaoliva de la PeÃ±a
Villaprovedo
Villaproviano
VillapÃºn
VillarÃ©n de Valdivia
Villarmentero de Campos
Villarmienzo
VillarrabÃ©
Villarramiel
Villarrobejo
Villarrodrigo de la Vega
Villasabariego de Ucieza
Villasarracino
Villasila de Valdavia
Villasur
Villatoquite
Villaturde
Villaumbrales
Villavega de Aguilar
Villavega de Ojeda
Villaverde de la PeÃ±a
Villaviudas
Villelga
Villemar
VillerÃ­as de Campos
Villodre
Villodrigo
Villoldo
Villorquite de Herrera
Villorquite del PÃ¡ramo
Villosilla de la Vega
Villota del Duque
Villota del PÃ¡ramo
Villotilla
Villovieco
Zona Residencial Camponecha
Zorita del PÃ¡ramo
""".strip()


def _repair_name(value):
    repaired = value
    for __attempt in range(3):
        if 'Ã' not in repaired and 'Â' not in repaired:
            break
        try:
            repaired = repaired.encode('latin1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
    return repaired


def get_localidad_names():
    seen = set()
    names = []
    for raw_name in LOCALIDADES_RAW.splitlines():
        name = _repair_name(raw_name.strip())
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


class ZonaTrabajoLocalidad(models.Model):
    _name = 'zonastrabajo.localidad'
    _description = 'Localidad'
    _order = 'name, id'

    name = fields.Char(string='Localidad', required=True, index=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('zonastrabajo_localidad_name_uniq', 'unique(name)', 'La localidad debe ser única.'),
    ]

    def init(self):
        super().init()
        locality_names = get_localidad_names()
        self.env.cr.execute(f"SELECT name FROM {self._table}")
        existing_names = {name for (name,) in self.env.cr.fetchall()}
        missing_names = [name for name in locality_names if name not in existing_names]
        if not missing_names:
            return

        self.env.cr.executemany(
            f"""
                INSERT INTO {self._table} (name, active, create_uid, write_uid, create_date, write_date)
                VALUES (%s, TRUE, 1, 1, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
            """,
            [(name,) for name in missing_names],
        )
