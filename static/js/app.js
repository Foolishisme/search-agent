import { cancelRun, createSkill, deleteSession as deleteSessionRequest, deleteSkill, fetchArtifact, fetchArtifacts, fetchRules, fetchSessionDetail, fetchSessions, fetchSkillDetail, fetchSkills, saveArtifact as saveArtifactRequest, saveRules, startAskStream, updateSkill } from './api.js';
import { bindCopyButtons, buildExpandableText, buildLogsBlock, buildResultLinkRow, buildSourceMeta, buildSourcesBlock, encodeCopyValue, escapeHtml, initRichRendering, renderMarkdown, renderMarkdownInto, renderRichBlocksIn } from './rendering.js';

        const submitButton = document.getElementById('submit');
        const newSessionButton = document.getElementById('new-session');
        const toggleHistoryButton = document.getElementById('toggle-history');
        const deleteSessionButton = document.getElementById('delete-session');
        const attachTrigger = document.getElementById('attach-trigger');
        const fileInput = document.getElementById('file-input');
        const questionInput = document.getElementById('question');
        const liveAnswerCardElement = document.querySelector('.answer-card');
        const liveLogsElement = document.getElementById('live-logs');
        const answerElement = document.getElementById('answer');
        const sourcesElement = document.getElementById('sources');
        const sourcesListElement = document.getElementById('sources-list');
        const sourcesCountTextElement = document.getElementById('sources-count-text');
        const logsElement = document.getElementById('logs');
        const resultsElement = document.getElementById('results');
        const logsCountElement = document.getElementById('logs-count');
        const resultsCountElement = document.getElementById('results-count');
        const logsPanel = document.getElementById('logs-panel');
        const resultsPanel = document.getElementById('results-panel');
        const statusElement = document.getElementById('status');
        const errorElement = document.getElementById('error');
        const conversationElement = document.getElementById('conversation');
        const sessionListElement = document.getElementById('session-list');
        const openRulesButton = document.getElementById('open-rules');
        const newSkillButton = document.getElementById('new-skill');
        const skillListElement = document.getElementById('skill-list');
        const agentConfigCardElement = document.getElementById('agent-config-card');
        const configTitleElement = document.getElementById('config-title');
        const configMetaElement = document.getElementById('config-meta');
        const configModeElement = document.getElementById('config-mode');
        const configContentElement = document.getElementById('config-content');
        const configContentLabelElement = document.getElementById('config-content-label');
        const configStatusElement = document.getElementById('config-status');
        const configErrorElement = document.getElementById('config-error');
        const saveConfigButton = document.getElementById('save-config');
        const deleteSkillButton = document.getElementById('delete-skill');
        const skillNameFieldElement = document.getElementById('skill-name-field');
        const skillDescriptionFieldElement = document.getElementById('skill-description-field');
        const skillEnabledFieldElement = document.getElementById('skill-enabled-field');
        const skillNameInput = document.getElementById('skill-name-input');
        const skillDescriptionInput = document.getElementById('skill-description-input');
        const skillEnabledInput = document.getElementById('skill-enabled-input');
        const layoutElement = document.querySelector('.layout');
        const mainGridElement = document.querySelector('.main-grid');
        const composerContainerElement = document.querySelector('.floating-composer');
        const sessionToolbarCardElement = document.querySelector('.session-toolbar-card');
        const sessionMetaElement = document.getElementById('session-meta');
        const sessionAttachmentsElement = document.getElementById('session-attachments');
        const pendingAttachmentsElement = document.getElementById('pending-attachments');
        const canvasUsedTag = document.getElementById('canvas-used-tag');
        const artifactShellElement = document.querySelector('.artifact-shell');
        const createArtifactButton = document.getElementById('create-artifact');
        const artifactPanelElement = document.getElementById('artifact-panel');
        const artifactListElement = document.getElementById('artifact-list');
        const artifactEditorElement = document.getElementById('artifact-editor');
        const artifactSummaryMetaElement = document.getElementById('artifact-summary-meta');
        const artifactPanelLabelElement = document.getElementById('artifact-panel-label');
        const artifactPanelStatusElement = document.getElementById('artifact-panel-status');
        const artifactTitleInput = document.getElementById('artifact-title');
        const artifactContentInput = document.getElementById('artifact-content');
        const artifactPreviewElement = document.getElementById('artifact-preview');
        const saveArtifactButton = document.getElementById('save-artifact');
        const artifactSaveStateElement = document.getElementById('artifact-save-state');
        const downloadArtifactLink = document.getElementById('download-artifact');

        let currentSessionId = null;
        let currentSessionTitle = '新会话';
        let pendingFiles = [];
        let latestAnswerMarkdown = '';
        let latestSearchResults = [];
        let currentArtifactId = null;
        let currentArtifacts = [];
        let isArtifactDirty = false;
        let isRunActive = false;
        let activeRunId = null;
        let activeRunBaseSessionId = null;
        let currentConfigMode = null;
        let currentSkillId = null;


        initRichRendering();

        const copyHandlers = {
            setStatus(message) {
                statusElement.textContent = message;
            },
            setError(message) {
                errorElement.textContent = message;
            },
        };

        function autosizeQuestionInput() {
            questionInput.style.height = 'auto';
            const nextHeight = Math.min(questionInput.scrollHeight, 220);
            questionInput.style.height = `${Math.max(nextHeight, 40)}px`;
            questionInput.style.overflowY = questionInput.scrollHeight > 220 ? 'auto' : 'hidden';
        }

        function updateHistoryToggle() {
            const collapsed = layoutElement.classList.contains('sidebar-collapsed');
            toggleHistoryButton.textContent = collapsed ? '显示历史' : '隐藏历史';
        }

        function toggleHistorySidebar() {
            layoutElement.classList.toggle('sidebar-collapsed');
            updateHistoryToggle();
        }

        function setSessionMeta() {
            sessionMetaElement.textContent = `当前会话：${currentSessionTitle}`;
            deleteSessionButton.disabled = !currentSessionId;
            updateArtifactEntryButton();
        }

        function beginActiveRun(baseSessionId) {
            isRunActive = true;
            activeRunId = null;
            activeRunBaseSessionId = baseSessionId;
            submitButton.textContent = '中断';
            submitButton.disabled = false;
        }

        function finishActiveRun() {
            isRunActive = false;
            activeRunId = null;
            activeRunBaseSessionId = null;
            submitButton.textContent = '发送问题';
            submitButton.disabled = false;
        }

        async function requestCancelRun() {
            if (!activeRunId) {
                return;
            }
            submitButton.textContent = '停止中...';
            submitButton.disabled = true;
            statusElement.textContent = '正在停止当前执行...';
            try {
                await cancelRun(activeRunId);
            } catch (error) {
                errorElement.textContent = error.message || '停止执行失败';
                submitButton.textContent = '中断';
                submitButton.disabled = false;
            }
        }

        function setCanvasUsed(toolObservations) {
            const used = (toolObservations || []).some((item) => (
                item.status === 'success'
                && (item.tool === 'canvas' || item.tool === 'save_markdown_artifact')
            ));
            canvasUsedTag.classList.toggle('hidden', !used);
        }

        function updateArtifactEntryButton() {
            const hasArtifacts = currentArtifacts.length > 0;
            createArtifactButton.textContent = hasArtifacts ? '打开 Canvas' : '生成 MD';
            createArtifactButton.disabled = hasArtifacts
                ? !currentSessionId
                : !(currentSessionId && latestAnswerMarkdown.trim());
            artifactSummaryMetaElement.textContent = hasArtifacts
                ? '已生成 Markdown 文档，点开可继续编辑或下载。'
                : '把当前答案转成可编辑 Markdown 文档。';
        }

        function updateArtifactPanelState() {
            const activeArtifact = currentArtifacts.find((item) => item.artifact_id === currentArtifactId) || currentArtifacts[0] || null;
            artifactPanelLabelElement.textContent = activeArtifact ? activeArtifact.title : '尚未生成文档';
            artifactPanelStatusElement.textContent = activeArtifact
                ? (isArtifactDirty ? '有未保存修改' : '已保存，可继续下载')
                : '生成后在这里继续修改';
            updateArtifactEntryButton();
        }

        function setArtifactDirty(dirty) {
            isArtifactDirty = Boolean(dirty && currentArtifactId);
            saveArtifactButton.classList.toggle('hidden', !isArtifactDirty);
            artifactSaveStateElement.textContent = currentArtifactId
                ? (isArtifactDirty ? '有未保存修改' : '已保存')
                : '尚未生成文档';
            updateArtifactPanelState();
        }

        function resetArtifactEditor() {
            currentArtifactId = null;
            artifactEditorElement.classList.add('hidden');
            artifactTitleInput.value = '';
            artifactContentInput.value = '';
            artifactPreviewElement.innerHTML = '<p class="placeholder">请选择文档。</p>';
            downloadArtifactLink.href = '#';
            downloadArtifactLink.setAttribute('download', 'document.md');
            setArtifactDirty(false);
            updateArtifactPanelState();
        }

        function renderArtifactPreview() {
            renderMarkdownInto(artifactPreviewElement, artifactContentInput.value);
        }

        function renderArtifactList(artifacts) {
            currentArtifacts = artifacts;
            artifactListElement.innerHTML = '';
            if (!artifacts.length) {
                artifactListElement.innerHTML = '<span class="placeholder">当前会话还没有文档。</span>';
                updateArtifactPanelState();
                return;
            }

            artifacts.forEach((artifact) => {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = `artifact-item${artifact.artifact_id === currentArtifactId ? ' active' : ''}`;
                item.textContent = artifact.title;
                item.addEventListener('click', () => loadArtifact(artifact.artifact_id));
                artifactListElement.appendChild(item);
            });
            updateArtifactPanelState();
        }

        function renderSessionAttachments(attachments) {
            sessionAttachmentsElement.innerHTML = '';
            if (!attachments.length) {
                sessionAttachmentsElement.innerHTML = '<span class="placeholder">当前会话还没有附件。</span>';
                return;
            }

            attachments.forEach((attachment) => {
                const chip = document.createElement('span');
                chip.className = 'attachment-chip';
                chip.textContent = `${attachment.filename}`;
                sessionAttachmentsElement.appendChild(chip);
            });
        }

        function renderPendingFiles() {
            pendingAttachmentsElement.innerHTML = '';
            if (!pendingFiles.length) {
                pendingAttachmentsElement.innerHTML = '<span class="placeholder">未选择附件。</span>';
                return;
            }

            pendingFiles.forEach((file, index) => {
                const chip = document.createElement('span');
                chip.className = 'attachment-chip';
                chip.innerHTML = `
                    <span>${escapeHtml(file.name)}</span>
                    <button type="button" class="chip-remove" data-index="${index}">移除</button>
                `;
                const removeButton = chip.querySelector('[data-index]');
                removeButton.addEventListener('click', () => {
                    pendingFiles = pendingFiles.filter((_, itemIndex) => itemIndex !== index);
                    renderPendingFiles();
                });
                pendingAttachmentsElement.appendChild(chip);
            });
        }
        function resetRoundOutput() {
            latestSearchResults = [];
            renderLiveLogs([]);
            answerElement.innerHTML = '<p class="placeholder">等待提问...</p>';
            hideLiveAnswer();
            sourcesElement.hidden = true;
            sourcesElement.open = false;
            sourcesListElement.innerHTML = '';
            sourcesCountTextElement.textContent = '0 条来源';
            renderLogs([]);
            statusElement.textContent = '';
            errorElement.textContent = '';
            setCanvasUsed([]);
        }

        function startNewSession() {
            currentSessionId = null;
            currentSessionTitle = '新会话';
            questionInput.value = '';
            autosizeQuestionInput();
            pendingFiles = [];
            latestAnswerMarkdown = '';
            latestSearchResults = [];
            currentArtifacts = [];
            conversationElement.innerHTML = '<div class="placeholder">还没有对话记录，发送第一条消息后会自动创建会话。</div>';
            resetRoundOutput();
            setSessionMeta();
            renderSessionAttachments([]);
            renderPendingFiles();
            renderArtifactList([]);
            resetArtifactEditor();
            artifactPanelElement.open = false;
        }

        function renderSkillList(skills) {
            skillListElement.innerHTML = '';
            if (!skills.length) {
                skillListElement.innerHTML = '<div class="placeholder">还没有 skills。</div>';
                return;
            }

            skills.forEach((skill) => {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = `skill-item${skill.skill_id === currentSkillId ? ' active' : ''}`;
                item.innerHTML = `
                    <div class="skill-item-head">
                        <span class="skill-item-title">#${skill.seq} ${escapeHtml(skill.name)}</span>
                        <span class="skill-item-meta">${skill.enabled ? '启用' : '停用'}</span>
                    </div>
                    <div class="skill-item-meta">${escapeHtml(skill.description || '暂无描述')}</div>
                `;
                item.addEventListener('click', () => {
                    void loadSkillDetail(skill.skill_id);
                });
                skillListElement.appendChild(item);
            });
        }

        async function loadSkills() {
            try {
                renderSkillList(await fetchSkills());
            } catch (error) {
                skillListElement.innerHTML = '<div class="placeholder">加载 skills 失败。</div>';
            }
        }

        async function loadSkillDetail(skillId) {
            openConfigPanel('skill');
            const data = await fetchSkillDetail(skillId);
            currentSkillId = data.skill_id;
            skillNameInput.value = data.name || '';
            skillDescriptionInput.value = data.description || '';
            skillEnabledInput.checked = Boolean(data.enabled);
            configContentElement.value = data.content || '';
            openConfigPanel('skill');
            await loadSkills();
        }

        function prepareNewSkill() {
            currentSkillId = null;
            skillNameInput.value = '';
            skillDescriptionInput.value = '';
            skillEnabledInput.checked = true;
            configContentElement.value = '';
            openConfigPanel('skill');
        }

        function openConfigPanel(mode) {
            currentConfigMode = mode;
            agentConfigCardElement.classList.remove('hidden');
            configModeElement.textContent = mode === 'rules' ? 'rules' : 'skill';
            configErrorElement.textContent = '';
            configStatusElement.textContent = '';
            const showSkillFields = mode === 'skill';
            skillNameFieldElement.hidden = !showSkillFields;
            skillDescriptionFieldElement.hidden = !showSkillFields;
            skillEnabledFieldElement.hidden = !showSkillFields;
            skillNameFieldElement.classList.toggle('hidden', !showSkillFields);
            skillDescriptionFieldElement.classList.toggle('hidden', !showSkillFields);
            skillEnabledFieldElement.classList.toggle('hidden', !showSkillFields);
            deleteSkillButton.classList.toggle('hidden', !showSkillFields || !currentSkillId);

            if (mode === 'rules') {
                configTitleElement.textContent = 'Global Rules';
                configMetaElement.textContent = '每轮请求都会默认带入这些全局规则。';
                configContentLabelElement.textContent = 'Rules 内容';
                configContentElement.placeholder = '在这里维护全局规则';
            } else {
                configTitleElement.textContent = currentSkillId ? '编辑 Skill' : '新建 Skill';
                configMetaElement.textContent = 'Skill 是动态上下文，不是可执行工具。';
                configContentLabelElement.textContent = 'SKILL 内容';
                configContentElement.placeholder = '在这里维护 skill 内容';
            }
        }

        async function loadRules() {
            currentSkillId = null;
            skillNameInput.value = '';
            skillDescriptionInput.value = '';
            skillEnabledInput.checked = true;
            const data = await fetchRules();
            openConfigPanel('rules');
            configContentElement.value = data.content || '';
            await loadSkills();
        }

        async function saveAgentConfig() {
            configErrorElement.textContent = '';
            configStatusElement.textContent = '';

            if (currentConfigMode === 'rules') {
                await saveRules(configContentElement.value);
                configStatusElement.textContent = 'Rules 已保存';
                return;
            }

            if (currentConfigMode === 'skill') {
                const payload = {
                    name: skillNameInput.value.trim(),
                    description: skillDescriptionInput.value.trim(),
                    content: configContentElement.value,
                    enabled: skillEnabledInput.checked,
                };
                if (!payload.name) {
                    throw new Error('Skill 名称不能为空');
                }

                const data = currentSkillId
                    ? await updateSkill(currentSkillId, payload)
                    : await createSkill(payload);
                currentSkillId = data.skill_id;
                configStatusElement.textContent = 'Skill 已保存';
                openConfigPanel('skill');
                await loadSkills();
            }
        }

        async function removeCurrentSkill() {
            if (!currentSkillId) {
                return;
            }
            await deleteSkill(currentSkillId);
            currentSkillId = null;
            agentConfigCardElement.classList.add('hidden');
            await loadSkills();
        }

        function renderLogs(logs) {
            logsElement.innerHTML = '';
            logsCountElement.textContent = String(logs.length);
            if (!logs.length) {
                logsElement.innerHTML = '<div class="placeholder">当前没有执行日志。</div>';
                logsPanel.open = false;
                return;
            }
            logs.forEach((log) => {
                const item = document.createElement('div');
                item.className = 'log-item';
                item.textContent = `[${log.stage}] ${log.message}`;
                logsElement.appendChild(item);
            });
        }

        function renderLiveLogs(logs) {
            liveLogsElement.innerHTML = '';
            if (!logs.length) {
                liveLogsElement.classList.add('hidden');
                return;
            }
            const block = buildLogsBlock(logs, { open: true, className: 'message-logs', title: '本轮执行日志' });
            if (!block) {
                liveLogsElement.classList.add('hidden');
                return;
            }
            liveLogsElement.appendChild(block);
            liveLogsElement.classList.remove('hidden');
        }

        function renderResults(results) {
            resultsElement.innerHTML = '';
            resultsCountElement.textContent = String(results.length);
            if (!results.length) {
                resultsElement.innerHTML = '<div class="placeholder">当前没有搜索结果。</div>';
                resultsPanel.open = false;
                return;
            }

            results.forEach((result) => {
                const item = document.createElement('div');
                item.className = 'result-item';

                const title = document.createElement('strong');
                title.textContent = result.title || '未命名来源';
                item.appendChild(title);
                item.appendChild(buildExpandableText(result.snippet || '暂无摘要', 'meta'));
                item.appendChild(buildResultLinkRow(result));

                resultsElement.appendChild(item);
            });
        }

        function renderSources(results) {
            sourcesListElement.innerHTML = '';
            if (!results.length) {
                sourcesElement.hidden = true;
                sourcesElement.open = false;
                sourcesCountTextElement.textContent = '0 条来源';
                return;
            }

            results.forEach((result, index) => {
                const item = document.createElement('details');
                item.className = 'source-item';

                const titleRow = document.createElement('summary');
                titleRow.className = 'source-item-toggle';
                titleRow.innerHTML = `
                    <span class="source-index">${index + 1}</span>
                    <span class="source-title">${escapeHtml(result.title || '未命名来源')}</span>
                `;
                item.appendChild(titleRow);

                const body = document.createElement('div');
                body.className = 'source-item-body';
                body.appendChild(buildExpandableText(result.snippet || '暂无摘要', 'source-snippet'));
                body.appendChild(buildSourceMeta(result));
                item.appendChild(body);

                sourcesListElement.appendChild(item);
            });
            sourcesCountTextElement.textContent = `${results.length} 条来源`;
            sourcesElement.hidden = false;
            sourcesElement.open = false;
        }

        function showLiveAnswer() {
            renderLiveLogs([]);
            liveAnswerCardElement.classList.remove('hidden');
        }

        function hideLiveAnswer() {
            liveAnswerCardElement.classList.add('hidden');
        }

        function renderTurns(turns = [], latestResults = []) {
            conversationElement.innerHTML = '';
            if (!turns.length) {
                conversationElement.innerHTML = '<div class="placeholder">当前会话为空。</div>';
                return;
            }

            turns.forEach((turn, index) => {
                const userItem = document.createElement('div');
                userItem.className = 'message user';
                userItem.innerHTML = `
                    <div class="message-role">
                        <div class="message-role-main">
                            <span>用户</span>
                            <span>${escapeHtml(turn.created_at || '')}</span>
                        </div>
                        <div class="message-role-actions">
                            <button class="copy-message" type="button" data-copy-text="${encodeCopyValue(turn.question || '')}">复制</button>
                        </div>
                    </div>
                    <div class="message-content">${escapeHtml(turn.question || '')}</div>
                `;
                conversationElement.appendChild(userItem);

                const assistantItem = document.createElement('div');
                assistantItem.className = 'message assistant';
                assistantItem.innerHTML = `
                    <div class="message-role">
                        <div class="message-role-main">
                            <span>Assistant</span>
                            <span>${escapeHtml(turn.created_at || '')}</span>
                        </div>
                        <div class="message-role-actions">
                            <button class="copy-message" type="button" data-copy-text="${encodeCopyValue(turn.answer || '')}">复制</button>
                        </div>
                    </div>
                    <div class="markdown-content">${renderMarkdown(turn.answer || '')}</div>
                `;

                const logsBlock = buildLogsBlock(Array.isArray(turn.logs) ? turn.logs : [], {
                    open: false,
                    className: 'message-logs',
                    title: '本轮执行日志',
                });
                if (logsBlock) {
                    assistantItem.appendChild(logsBlock);
                }

                const turnResults = Array.isArray(turn.search_results) ? turn.search_results : [];
                if (turnResults.length) {
                    assistantItem.appendChild(buildSourcesBlock(turnResults));
                } else if (index === turns.length - 1 && latestResults.length) {
                    assistantItem.appendChild(buildSourcesBlock(latestResults));
                }

                conversationElement.appendChild(assistantItem);
            });
            void renderRichBlocksIn(conversationElement);
            bindCopyButtons(conversationElement, copyHandlers);
        }

        function renderConversation(messages, latestResults = []) {
            conversationElement.innerHTML = '';
            if (!messages.length) {
                conversationElement.innerHTML = '<div class="placeholder">当前会话为空。</div>';
                return;
            }

            let latestAssistantIndex = -1;
            for (let index = messages.length - 1; index >= 0; index -= 1) {
                if (messages[index].role === 'assistant') {
                    latestAssistantIndex = index;
                    break;
                }
            }

            messages.forEach((message, index) => {
                const item = document.createElement('div');
                item.className = `message ${message.role}`;
                const renderedContent = message.role === 'assistant'
                    ? `<div class="markdown-content">${renderMarkdown(message.content || '')}</div>`
                    : `<div class="message-content">${escapeHtml(message.content || '')}</div>`;
                item.innerHTML = `
                    <div class="message-role">
                        <div class="message-role-main">
                            <span>${message.role === 'user' ? '用户' : 'Assistant'}</span>
                            <span>${escapeHtml(message.created_at || '')}</span>
                        </div>
                        <div class="message-role-actions">
                            <button class="copy-message" type="button" data-copy-text="${encodeCopyValue(message.content || '')}">复制</button>
                        </div>
                    </div>
                    ${renderedContent}
                `;
                if (message.role === 'assistant' && index === latestAssistantIndex && latestResults.length) {
                    item.appendChild(buildSourcesBlock(latestResults));
                }
                conversationElement.appendChild(item);
            });
            void renderRichBlocksIn(conversationElement);
            bindCopyButtons(conversationElement, copyHandlers);
        }

        function initializeConversationLayout() {
            if (artifactShellElement && sessionToolbarCardElement && artifactShellElement.parentElement !== sessionToolbarCardElement) {
                sessionToolbarCardElement.appendChild(artifactShellElement);
            }
            if (composerContainerElement && mainGridElement && composerContainerElement.parentElement !== mainGridElement) {
                const firstSideCard = mainGridElement.querySelector('.side-card');
                if (firstSideCard) {
                    mainGridElement.insertBefore(composerContainerElement, firstSideCard);
                } else {
                    mainGridElement.appendChild(composerContainerElement);
                }
            }
            sourcesElement.classList.add('hidden');
            hideLiveAnswer();
            const resultsCard = resultsPanel.closest('.side-card');
            if (resultsCard) {
                resultsCard.classList.add('hidden');
            }
            const logsCard = logsPanel.closest('.side-card');
            if (logsCard) {
                logsCard.classList.add('hidden');
            }
            autosizeQuestionInput();
        }

        async function loadSessions() {
            try {
                renderSessionList(await fetchSessions());
            } catch (error) {
                sessionListElement.innerHTML = `<div class="placeholder">${error.message || '加载会话失败'}</div>`;
            }
        }

        async function loadArtifacts(sessionId, { openLatest = false } = {}) {
            if (!sessionId) {
                renderArtifactList([]);
                resetArtifactEditor();
                artifactPanelElement.open = false;
                return;
            }

            const artifacts = await fetchArtifacts(sessionId);
            renderArtifactList(artifacts);
            if (!artifacts.length) {
                resetArtifactEditor();
                artifactPanelElement.open = false;
                return;
            }

            if (openLatest || !currentArtifactId || !artifacts.some((item) => item.artifact_id === currentArtifactId)) {
                await loadArtifact(artifacts[0].artifact_id);
            } else {
                renderArtifactList(artifacts);
            }
        }

        async function loadArtifact(artifactId) {
            if (!currentSessionId) {
                return;
            }
            const data = await fetchArtifact(currentSessionId, artifactId);
            currentArtifactId = data.artifact_id;
            artifactEditorElement.classList.remove('hidden');
            artifactTitleInput.value = data.title;
            artifactContentInput.value = data.content;
            downloadArtifactLink.href = `/api/sessions/${currentSessionId}/artifacts/${artifactId}/download`;
            downloadArtifactLink.setAttribute('download', data.filename);
            renderArtifactPreview();
            artifactPanelElement.open = true;
            setArtifactDirty(false);
            renderArtifactList(await fetchArtifacts(currentSessionId));
        }

        function renderSessionList(sessions) {
            sessionListElement.innerHTML = '';
            if (!sessions.length) {
                sessionListElement.innerHTML = '<div class="placeholder">还没有历史会话。</div>';
                return;
            }

            sessions.forEach((session) => {
                const item = document.createElement('div');
                item.className = `session-item${session.session_id === currentSessionId ? ' active' : ''}`;
                item.addEventListener('click', () => loadSessionDetail(session.session_id));
                item.innerHTML = `
                    <div class="session-item-head">
                        <div class="session-title">${escapeHtml(session.title)}</div>
                        <button class="danger small" data-session-id="${escapeHtml(session.session_id)}">删除对话</button>
                    </div>
                    <div class="session-preview">${escapeHtml(session.last_message_preview || '暂无摘要')}</div>
                    <div class="session-time">${escapeHtml(session.updated_at)}</div>
                `;
                const deleteButton = item.querySelector('[data-session-id]');
                deleteButton.addEventListener('click', async (event) => {
                    event.stopPropagation();
                    await deleteSession(session.session_id);
                });
                sessionListElement.appendChild(item);
            });
        }

        async function loadSessionDetail(sessionId) {
            errorElement.textContent = '';
            try {
                const data = await fetchSessionDetail(sessionId);
                currentSessionId = data.session_id;
                currentSessionTitle = data.title;
                latestAnswerMarkdown = data.messages?.length
                    ? String(data.messages[data.messages.length - 1].content || '')
                    : '';
                latestSearchResults = data.latest_search_results || [];
                setSessionMeta();
                renderTurns(data.turns || [], latestSearchResults);
                hideLiveAnswer();
                renderLiveLogs([]);
                renderSessionAttachments(data.attachments || []);
                setCanvasUsed(data.latest_tool_observations || []);
                await loadArtifacts(data.session_id);
                statusElement.textContent = `已加载会话：${data.title}`;
                await loadSessions();
            } catch (error) {
                errorElement.textContent = error.message || '加载会话失败';
            }
        }

        async function deleteSession(sessionId) {
            errorElement.textContent = '';
            try {
                await deleteSessionRequest(sessionId);
                if (currentSessionId === sessionId) {
                    startNewSession();
                }
                await loadSessions();
            } catch (error) {
                errorElement.textContent = error.message || '删除会话失败';
            }
        }

        async function handleSubmit() {
            const question = questionInput.value.trim();
            const baseSessionId = currentSessionId;
            errorElement.textContent = '';
            if (!question) {
                errorElement.textContent = '请输入问题';
                return;
            }

            submitButton.disabled = true;
            beginActiveRun(baseSessionId);
            showLiveAnswer();
            statusElement.textContent = '执行中...';
            answerElement.innerHTML = '<p class="placeholder">处理中...</p>';
            latestSearchResults = [];
            renderLogs([]);

            try {
                const formData = new FormData();
                formData.append('question', question);
                if (currentSessionId) {
                    formData.append('session_id', currentSessionId);
                }
                pendingFiles.forEach((file) => {
                    formData.append('files', file, file.name);
                });

                const response = await startAskStream(formData);

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let liveLogs = [];
                let liveToolObservations = [];

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) {
                        break;
                    }

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (!line.trim()) {
                            continue;
                        }

                        const event = JSON.parse(line);
                        if (event.type === 'run_started') {
                            activeRunId = event.run_id || null;
                        } else if (event.type === 'status') {
                            statusElement.textContent = event.message || '';
                        } else if (event.type === 'log') {
                            liveLogs.push(event.log);
                            renderLiveLogs(liveLogs);
                        } else if (event.type === 'tool_result') {
                            liveToolObservations.push(event.result);
                            setCanvasUsed(liveToolObservations);
                        } else if (event.type === 'results') {
                            latestSearchResults = event.results || [];
                        } else if (event.type === 'attachments') {
                            renderSessionAttachments(event.attachments || []);
                        } else if (event.type === 'final') {
                            const data = event.data;
                            currentSessionId = data.session_id;
                            currentSessionTitle = data.session_title;
                            latestAnswerMarkdown = data.answer || '';
                            latestSearchResults = data.search_results || [];
                            setSessionMeta();
                            await loadSessionDetail(data.session_id);
                            statusElement.textContent = data.need_search
                                ? `已完成，触发搜索：${data.query || ''}`
                                : '已完成，未触发搜索';
                            questionInput.value = '';
                            autosizeQuestionInput();
                            pendingFiles = [];
                            renderPendingFiles();
                            finishActiveRun();
                        } else if (event.type === 'cancelled') {
                            if (activeRunBaseSessionId) {
                                await loadSessionDetail(activeRunBaseSessionId);
                            } else {
                                startNewSession();
                            }
                            statusElement.textContent = event.message || '已停止当前执行';
                            finishActiveRun();
                        } else if (event.type === 'error') {
                            throw new Error(event.message || '发生未知错误');
                        }
                    }
                }
            } catch (error) {
                answerElement.innerHTML = '<p class="placeholder">请求失败</p>';
                hideLiveAnswer();
                errorElement.textContent = error.message || '发生未知错误';
                finishActiveRun();
            } finally {
                submitButton.disabled = false;
            }
        }

        submitButton.addEventListener('click', async () => {
            if (isRunActive) {
                await requestCancelRun();
                return;
            }
            await handleSubmit();
        });

        newSessionButton.addEventListener('click', startNewSession);
        deleteSessionButton.addEventListener('click', async () => {
            if (!currentSessionId) {
                return;
            }
            await deleteSession(currentSessionId);
        });
        openRulesButton.addEventListener('click', async () => {
            try {
                await loadRules();
            } catch (error) {
                configErrorElement.textContent = error.message || '加载 rules 失败';
            }
        });
        newSkillButton.addEventListener('click', prepareNewSkill);
        saveConfigButton.addEventListener('click', async () => {
            try {
                await saveAgentConfig();
            } catch (error) {
                configErrorElement.textContent = error.message || '保存失败';
            }
        });
        deleteSkillButton.addEventListener('click', async () => {
            try {
                await removeCurrentSkill();
            } catch (error) {
                configErrorElement.textContent = error.message || '删除 skill 失败';
            }
        });
        toggleHistoryButton.addEventListener('click', toggleHistorySidebar);

        attachTrigger.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', () => {
            const allowed = ['.pdf', '.txt', '.md'];
            const chosen = Array.from(fileInput.files || []).filter((file) =>
                allowed.some((suffix) => file.name.toLowerCase().endsWith(suffix))
            );
            pendingFiles = [...pendingFiles, ...chosen];
            renderPendingFiles();
            fileInput.value = '';
        });
        questionInput.addEventListener('input', autosizeQuestionInput);
        questionInput.addEventListener('keydown', (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                event.preventDefault();
                if (isRunActive) {
                    requestCancelRun();
                    return;
                }
                handleSubmit();
            }
        });
        artifactContentInput.addEventListener('input', renderArtifactPreview);
        artifactTitleInput.addEventListener('input', () => setArtifactDirty(true));
        artifactContentInput.addEventListener('input', () => setArtifactDirty(true));
        createArtifactButton.addEventListener('click', async () => {
            if (!currentSessionId) {
                return;
            }
            if (currentArtifacts.length) {
                artifactPanelElement.open = true;
                if (!currentArtifactId && currentArtifacts[0]) {
                    await loadArtifact(currentArtifacts[0].artifact_id);
                }
                return;
            }
            if (!latestAnswerMarkdown.trim()) {
                return;
            }
            try {
                const data = await saveArtifactRequest(
                    currentSessionId,
                    {
                        title: `${currentSessionTitle} 文档`,
                        content: latestAnswerMarkdown,
                    },
                    '创建文档失败',
                );
                currentArtifactId = data.artifact_id;
                await loadArtifacts(currentSessionId, { openLatest: true });
                artifactPanelElement.open = true;
            } catch (error) {
                errorElement.textContent = error.message || '创建文档失败';
            }
        });
        saveArtifactButton.addEventListener('click', async () => {
            if (!currentSessionId || !currentArtifactId) {
                return;
            }
            try {
                const data = await saveArtifactRequest(
                    currentSessionId,
                    {
                        title: artifactTitleInput.value,
                        content: artifactContentInput.value,
                        artifact_id: currentArtifactId,
                    },
                    '保存文档失败',
                );
                currentArtifactId = data.artifact_id;
                artifactTitleInput.value = data.title;
                artifactContentInput.value = data.content;
                downloadArtifactLink.href = `/api/sessions/${currentSessionId}/artifacts/${currentArtifactId}/download`;
                downloadArtifactLink.setAttribute('download', data.filename);
                renderArtifactPreview();
                setArtifactDirty(false);
                await loadArtifacts(currentSessionId);
            } catch (error) {
                errorElement.textContent = error.message || '保存文档失败';
            }
        });

        initializeConversationLayout();
        updateHistoryToggle();
        startNewSession();
        renderLogs([]);
        renderPendingFiles();
        loadSessions();
        loadSkills();
