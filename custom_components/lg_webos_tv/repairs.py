"""Réparations corrigeables : « Fonction Économie d'énergie » en conflit avec
la luminosité adaptative, désactivée après confirmation de l'utilisateur."""

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class DesactiverEconomieEnergie(RepairsFlow):
    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict | None = None) -> FlowResult:
        if user_input is None:
            return self.async_show_form(step_id="confirm")
        entrees = self.hass.config_entries.async_loaded_entries(DOMAIN)
        fonction = entrees[0].runtime_data.luminosite_adaptative if entrees else None
        if fonction is None:
            return self.async_abort(reason="non_configuree")
        resultat = await fonction.desactiver_economie_energie("home_assistant")
        if not resultat["ok"]:
            return self.async_abort(reason="ecriture_echouee",
                                    description_placeholders={"raison": resultat["raison"]})
        # La Réparation se ferme d'elle-même à la notification du téléviseur.
        return self.async_create_entry(data={})


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str,
                                data: dict | None) -> RepairsFlow:
    return DesactiverEconomieEnergie()
