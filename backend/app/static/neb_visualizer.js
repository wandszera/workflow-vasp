function renderNEBChart(containerId, data, onImageClick) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const width = container.clientWidth || 500;
  const height = 300;
  const padding = { top: 30, right: 40, bottom: 55, left: 65 };

  const energies = data.relative_energies;
  const images = data.images;

  const minE = Math.min(...energies);
  const maxE = Math.max(...energies);
  const range = maxE - minE || 1.0;

  // Scale calculations
  const scaleX = (idx) => padding.left + (idx / (energies.length - 1)) * (width - padding.left - padding.right);
  const scaleY = (val) => height - padding.bottom - ((val - minE) / range) * (height - padding.top - padding.bottom);

  // Build the line path (smooth cubic splines if possible, or straight lines with beautiful styles)
  let linePath = `M ${scaleX(0)} ${scaleY(energies[0])}`;
  for (let i = 1; i < energies.length; i++) {
    linePath += ` L ${scaleX(i)} ${scaleY(energies[i])}`;
  }

  // Draw node circles and hover tooltips
  let nodesHtml = "";
  energies.forEach((energy, idx) => {
    const cx = scaleX(idx);
    const cy = scaleY(energy);
    nodesHtml += `
      <g class="neb-node" style="cursor: pointer;" onclick="window.onNEBNodeSelect(${idx}, '${images[idx]}')">
        <circle cx="${cx}" cy="${cy}" r="6" fill="#10b981" stroke="#fff" stroke-width="2" style="transition: all 0.2s;" />
        <circle cx="${cx}" cy="${cy}" r="12" fill="#10b981" opacity="0" class="hover-trigger" />
        <text x="${cx}" y="${cy - 12}" fill="#fff" font-size="0.7rem" text-anchor="middle" font-weight="600">${energy.toFixed(3)} eV</text>
        <text x="${cx}" y="${height - padding.bottom + 18}" fill="var(--text-muted)" font-size="0.75rem" text-anchor="middle">Imagem ${images[idx]}</text>
      </g>
    `;
  });

  // Store the callback globally so SVG inline onclick can find it
  window.onNEBNodeSelect = (idx, imageName) => {
    if (typeof onImageClick === 'function') {
      onImageClick(idx, imageName);
    }
  };

  const svg = `
    <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="background: transparent; font-family: 'Outfit', sans-serif;">
      <!-- Grid Lines -->
      <line x1="${padding.left}" y1="${scaleY(0.0)}" x2="${width - padding.right}" y2="${scaleY(0.0)}" stroke="rgba(255,255,255,0.08)" stroke-width="1.5" />
      
      <!-- Activation Energy line & text -->
      <line x1="${padding.left}" y1="${scaleY(maxE)}" x2="${width - padding.right}" y2="${scaleY(maxE)}" stroke="rgba(239, 68, 68, 0.3)" stroke-width="1" stroke-dasharray="2,2" />
      <text x="${width - padding.right - 10}" y="${scaleY(maxE) - 8}" fill="#ef4444" font-size="0.75rem" text-anchor="end" font-weight="600">
        Barreira (E_act): ${data.activation_energy.toFixed(3)} eV
      </text>

      <!-- Pathway Line -->
      <path d="${linePath}" fill="none" stroke="#6366f1" stroke-width="3" stroke-linecap="round" />

      <!-- Nodes -->
      ${nodesHtml}

      <!-- Axes -->
      <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />
      <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" />

      <!-- Y-axis Label -->
      <text x="${padding.left - 10}" y="${padding.top + 5}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="end">${maxE.toFixed(2)} eV</text>
      <text x="${padding.left - 10}" y="${height - padding.bottom}" fill="var(--text-muted)" font-size="0.7rem" text-anchor="end">${minE.toFixed(2)} eV</text>
      <text x="15" y="${height / 2}" fill="var(--text-muted)" font-size="0.8rem" text-anchor="middle" transform="rotate(-90 15 ${height / 2})">Energia Relativa (eV)</text>
    </svg>
  `;

  container.innerHTML = svg;
}
