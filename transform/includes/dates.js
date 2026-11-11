// "Hoy" para el estado de actualización (2.4): la variable as_of_date (AAAA-MM-DD) o la fecha actual en Santiago.
// La variable permite simular otra fecha sin esperarla: npx dataform run transform --vars=as_of_date=2026-12-03
function asOfDate() {
  const value = dataform.projectConfig.vars.as_of_date;
  if (!value) {
    return "CURRENT_DATE('America/Santiago')";
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw new Error(`as_of_date debe ser AAAA-MM-DD; llegó: ${value}`);
  }
  return `DATE '${value}'`;
}

module.exports = { asOfDate };
