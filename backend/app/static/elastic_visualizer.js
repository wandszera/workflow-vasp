function renderElasticData(matrixContainerId, moduliContainerId, data) {
  const matrixContainer = document.getElementById(matrixContainerId);
  const moduliContainer = document.getElementById(moduliContainerId);

  if (!matrixContainer || !moduliContainer) return;

  const C = data.matrix;
  const labels = ["XX", "YY", "ZZ", "XY", "YZ", "ZX"];

  // 1. Build stiffness matrix HTML table
  let tableHtml = `
    <table style="width: 100%; border-collapse: collapse; font-family: monospace; font-size: 0.9rem; color: #fff; text-align: center;">
      <thead>
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.1);">
          <th style="padding: 0.5rem; color: var(--text-muted);">C_ij (GPa)</th>
          ${labels.map(l => `<th style="padding: 0.5rem; font-weight: bold; color: #38bdf8;">${l}</th>`).join('')}
        </tr>
      </thead>
      <tbody>
  `;

  for (let i = 0; i < 6; i++) {
    tableHtml += `
      <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); hover: background-color: rgba(255,255,255,0.02);">
        <td style="padding: 0.5rem; font-weight: bold; color: #38bdf8; border-right: 1px solid rgba(255,255,255,0.1);">${labels[i]}</td>
    `;
    for (let j = 0; j < 6; j++) {
      const val = C[i][j];
      const isDiagonal = i === j;
      const isZero = Math.abs(val) < 0.01;
      
      // Compute shaded color
      let cellStyle = "padding: 0.5rem; transition: all 0.2s;";
      if (isDiagonal) {
        cellStyle += " background: rgba(99, 102, 241, 0.15); font-weight: bold; color: #818cf8;";
      } else if (isZero) {
        cellStyle += " color: rgba(255,255,255,0.25);";
      } else {
        cellStyle += " color: #cbd5e1;";
      }
      
      tableHtml += `<td style="${cellStyle}">${val.toFixed(1)}</td>`;
    }
    tableHtml += "</tr>";
  }
  tableHtml += "</tbody></table>";
  matrixContainer.innerHTML = tableHtml;

  // 2. Build macro mechanical properties grid
  const moduliHtml = `
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 1rem;">
      <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 1rem; border-radius: 8px; text-align: center;">
        <div style="font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600;">Modulo de Bulk (B)</div>
        <div style="font-size: 1.8rem; font-weight: bold; color: #6366f1; margin-top: 0.25rem;">${data.bulk_modulus.toFixed(1)} <span style="font-size: 0.9rem; font-weight: normal; color: var(--text-muted);">GPa</span></div>
      </div>

      <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 1rem; border-radius: 8px; text-align: center;">
        <div style="font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600;">Modulo de Cisalhamento (G)</div>
        <div style="font-size: 1.8rem; font-weight: bold; color: #10b981; margin-top: 0.25rem;">${data.shear_modulus.toFixed(1)} <span style="font-size: 0.9rem; font-weight: normal; color: var(--text-muted);">GPa</span></div>
      </div>

      <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 1rem; border-radius: 8px; text-align: center;">
        <div style="font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600;">Modulo de Young (E)</div>
        <div style="font-size: 1.8rem; font-weight: bold; color: #f59e0b; margin-top: 0.25rem;">${data.young_modulus.toFixed(1)} <span style="font-size: 0.9rem; font-weight: normal; color: var(--text-muted);">GPa</span></div>
      </div>

      <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 1rem; border-radius: 8px; text-align: center;">
        <div style="font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600;">Razao de Poisson (&nu;)</div>
        <div style="font-size: 1.8rem; font-weight: bold; color: #ec4899; margin-top: 0.25rem;">${data.poisson_ratio.toFixed(3)}</div>
      </div>
    </div>
  `;
  moduliContainer.innerHTML = moduliHtml;
}
