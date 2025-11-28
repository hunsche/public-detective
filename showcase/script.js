document.addEventListener('DOMContentLoaded', () => {
    const data = window.SHOWCASE_DATA || [];
    const grid = document.getElementById('analyses-grid');
    const modal = document.getElementById('detail-modal');
    const modalContent = document.getElementById('modal-content');
    const closeModalBtn = document.getElementById('close-modal');
    const closeModalBtnFooter = document.getElementById('close-modal-btn');
    const savePdfBtn = document.getElementById('save-pdf-btn');

    // --- Helper Functions ---
    const formatCurrency = (value) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
    const formatDate = (dateString) => {
        if (!dateString) return 'N/A';
        return new Date(dateString).toLocaleDateString('pt-BR');
    };
    const formatStatus = (status) => {
        const map = {
            'ANALYSIS_SUCCESSFUL': 'Análise Concluída',
            'Divulgada no PNCP': 'Divulgada no PNCP',
            'Homologada': 'Homologada'
        };
        return map[status] || status;
    };

    const formatCategory = (category) => {
        const map = {
            'SOBREPRECO': 'Sobrepreço',
            'RESTRICAO_COMPETITIVIDADE': 'Restrição à Competitividade',
            'FRACIONAMENTO_DESPESA': 'Fracionamento de Despesa',
            'DIRECIONAMENTO': 'Direcionamento',
            'SUPERFATURAMENTO': 'Superfaturamento',
            'JOGO_DE_PLANILHA': 'Jogo de Planilha'
        };
        return map[category] || category.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
    };

    const formatSourceType = (type) => {
        const map = {
            'VAREJO': 'Varejo',
            'B2B': 'Atacado / B2B',
            'OFICIAL': 'Site Oficial',
            'PAINEL_PRECOS': 'Painel de Preços',
            'BANCO_PRECOS': 'Banco de Preços',
            'OUTRO': 'Outro'
        };
        return map[type] || type;
    };

    // --- Statistics ---
    const totalAnalyses = data.length;
    const highRiskCount = data.filter(a => (a.risk_score || 0) >= 70).length;
    const totalSavings = data.reduce((sum, a) => {
        if (!a.red_flags) return sum;
        const savings = a.red_flags.reduce((s, f) => s + (parseFloat(f.potential_savings) || 0), 0);
        return sum + savings;
    }, 0);

    document.getElementById('total-analyses').textContent = totalAnalyses;
    document.getElementById('high-risk-count').textContent = highRiskCount;
    document.getElementById('total-savings').textContent = formatCurrency(totalSavings);

    // --- Render Grid ---
    data.forEach(analysis => {
        const card = document.createElement('div');
        card.className = 'analysis-card';
        card.onclick = () => openModal(analysis);

        const riskScore = analysis.risk_score || 0;
        let riskClass = 'low';
        if (riskScore >= 70) riskClass = 'critical';
        else if (riskScore >= 50) riskClass = 'high';
        else if (riskScore >= 30) riskClass = 'medium';

        const savings = analysis.red_flags ? analysis.red_flags.reduce((s, f) => s + (parseFloat(f.potential_savings) || 0), 0) : 0;
        const savingsText = savings > 0 ? `Economia: ${formatCurrency(savings)}` : '';

        const location = analysis.municipio && analysis.uf ? `${analysis.municipio} - ${analysis.uf}` : 'Localização N/A';
        const agency = analysis.orgao || 'Órgão N/A';

        card.innerHTML = `
            <div class="card-header">
                <span class="risk-badge ${riskClass}">Risco: ${riskScore}/100</span>
                <span class="card-date">${formatDate(analysis.analysis_date)}</span>
            </div>
            <h3 class="card-title">${analysis.procurement_control_number}</h3>
            <p class="card-summary" style="margin-bottom: 0.5rem; font-weight: 600; color: var(--text-main);">${agency}</p>
            <div class="location-tag">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                    <circle cx="12" cy="10" r="3"></circle>
                </svg>
                ${location}
            </div>
            <p class="card-summary" style="margin-top: 1rem;">${analysis.analysis_summary || 'Sem resumo disponível.'}</p>
            <div class="card-footer">
                <div class="risk-score">
                    <div class="score-circle" style="color: var(--risk-${riskClass === 'critical' ? 'critical' : riskClass === 'high' ? 'medium' : riskClass === 'medium' ? 'low' : 'low'})">
                        ${riskScore}
                    </div>
                    <span style="font-size: 0.75rem; color: var(--text-muted)">Score</span>
                </div>
                <span class="savings-tag">${savingsText}</span>
            </div>
        `;
        grid.appendChild(card);
    });

    // --- Modal Logic ---
    function openModal(analysis) {
        const riskScore = analysis.risk_score || 0;
        let riskClass = 'low';
        if (riskScore >= 70) riskClass = 'critical';
        else if (riskScore >= 50) riskClass = 'high';
        else if (riskScore >= 30) riskClass = 'medium';

        const redFlagsHtml = (analysis.red_flags || []).map(flag => `
            <div class="red-flag-item">
                <div class="red-flag-header">
                    <span class="flag-category">${formatCategory(flag.category)}</span>
                    <span class="flag-severity ${flag.severity}">${flag.severity}</span>
                </div>
                <p class="detail-text">${flag.description}</p>
                <div class="evidence-box">"${flag.evidence_quote}"</div>
                <p class="detail-text" style="margin-top: 1rem; font-style: italic;">${flag.auditor_reasoning}</p>
                ${flag.potential_savings ? `<p style="color: var(--risk-low); font-weight: 600; margin-top: 0.5rem;">Economia Potencial: ${formatCurrency(parseFloat(flag.potential_savings))}</p>` : ''}
                
                <div class="sources-list" style="display: flex; flex-direction: column; gap: 0.5rem; margin-top: 1rem;">
                    ${(flag.sources || []).map(source => {
            const priceInfo = source.reference_price ? `${formatCurrency(source.reference_price)} (${source.price_unit || 'unidade'})` : '';
            const dateInfo = source.reference_date ? ` em ${formatDate(source.reference_date)}` : '';
            const details = [priceInfo, dateInfo].filter(Boolean).join(' ');

            return `
                        <div style="background: rgba(255,255,255,0.05); padding: 0.75rem; border-radius: 8px; border: 1px solid var(--border);">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                <span style="color: var(--primary); font-weight: 600; font-size: 0.875rem; display: flex; align-items: center; gap: 0.5rem;">
                                    ${source.name} (${formatSourceType(source.type)})
                                </span>
                                <span style="font-size: 0.75rem; color: var(--text-muted);">${details}</span>
                            </div>
                            ${source.rationale ? `<p style="font-size: 0.875rem; color: var(--text-muted); margin-top: 0.25rem;">${source.rationale}</p>` : ''}
                            ${source.evidence ? `<p style="font-size: 0.8rem; color: #6b7280; margin-top: 0.25rem; font-family: monospace;">"${source.evidence}"</p>` : ''}
                        </div>`;
        }).join('')}
                </div>
            </div>
        `).join('');

        // Collect all unique sources
        const allSources = new Map();
        if (analysis.grounding_metadata && analysis.grounding_metadata.sources) {
            analysis.grounding_metadata.sources.forEach(s => {
                const url = s.resolved_url || s.original_url;
                if (url) allSources.set(url, s.title || url);
            });
        }

        const sourcesHtml = Array.from(allSources.entries()).map(([url, title]) => `
            <a href="${url}" target="_blank" class="source-tag" style="text-decoration: none; display: inline-flex; align-items: center; gap: 0.5rem; transition: all 0.2s;">
                ${title}
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                    <polyline points="15 3 21 3 21 9"></polyline>
                    <line x1="10" y1="14" x2="21" y2="3"></line>
                </svg>
            </a>
        `).join('');

        modalContent.innerHTML = `
            <div class="detail-header">
                <div class="detail-meta" style="justify-content: space-between; align-items: center;">
                    <div style="display: flex; gap: 1rem;">
                        <span class="risk-badge ${riskClass}">Risco Global: ${riskScore}</span>
                        <span class="risk-badge" style="background: rgba(255,255,255,0.1); color: white;">ID: ${analysis.analysis_id.slice(0, 8)}...</span>
                    </div>
                    ${analysis.link_oficial ? `
                    <a href="${analysis.link_oficial}" target="_blank" class="official-link-btn">
                        Ver no Portal Oficial
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                            <polyline points="15 3 21 3 21 9"></polyline>
                            <line x1="10" y1="14" x2="21" y2="3"></line>
                        </svg>
                    </a>` : ''}
                </div>
                
                <h2 class="detail-title">${analysis.procurement_control_number}</h2>
                <p class="detail-text" style="font-weight: 600; font-size: 1.1rem; margin-bottom: 1.5rem;">${analysis.orgao || ''}</p>
                
                <div class="meta-grid">
                    <div class="meta-item">
                        <label>Localização</label>
                        <span>${analysis.municipio || '-'} / ${analysis.uf || '-'}</span>
                    </div>
                    <div class="meta-item">
                        <label>Modalidade</label>
                        <span>${analysis.modalidade || '-'}</span>
                    </div>
                    <div class="meta-item">
                        <label>Data Publicação</label>
                        <span>${formatDate(analysis.data_publicacao)}</span>
                    </div>
                    <div class="meta-item">
                        <label>Status</label>
                        <span>${formatStatus(analysis.status_compra)}</span>
                    </div>
                    <div class="meta-item">
                        <label>Valor Estimado</label>
                        <span>${analysis.valor_estimado ? formatCurrency(analysis.valor_estimado) : 'N/A'}</span>
                    </div>
                </div>

                <p class="detail-text" style="font-size: 1.1rem;">${analysis.procurement_summary || ''}</p>
            </div>

            <h3 class="section-title">Resumo da Auditoria</h3>
            <p class="detail-text">${analysis.analysis_summary}</p>

            <h3 class="section-title">Racional do Risco</h3>
            <p class="detail-text">${analysis.risk_score_rationale}</p>

            <h3 class="section-title">Pontos de Atenção (${(analysis.red_flags || []).length})</h3>
            <div class="red-flags-list">
                ${redFlagsHtml || '<p class="detail-text">Nenhum ponto de atenção crítico identificado.</p>'}
            </div>

            ${sourcesHtml ? `
            <h3 class="section-title">Fontes Consultadas</h3>
            <div class="sources-list" style="margin-bottom: 2rem;">
                ${sourcesHtml}
            </div>` : ''}
        `;

        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeModal() {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }

    closeModalBtn.onclick = closeModal;
    closeModalBtnFooter.onclick = closeModal;

    modal.onclick = (e) => {
        if (e.target === modal) closeModal();
    };
});
