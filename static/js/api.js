async function parseJsonResponse(response, fallbackMessage) {
    let data = null;
    try {
        data = await response.json();
    } catch {
        data = null;
    }
    if (!response.ok) {
        throw new Error((data && data.detail) || fallbackMessage);
    }
    return data;
}

export async function fetchRules() {
    const response = await fetch('/api/agent/rules');
    return parseJsonResponse(response, '加载 rules 失败');
}

export async function saveRules(content) {
    const response = await fetch('/api/agent/rules', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
    });
    return parseJsonResponse(response, '保存 rules 失败');
}

export async function fetchSkills() {
    const response = await fetch('/api/agent/skills');
    return parseJsonResponse(response, '加载 skills 失败');
}

export async function fetchSkillDetail(skillId) {
    const response = await fetch(`/api/agent/skills/${skillId}`);
    return parseJsonResponse(response, '加载 skill 失败');
}

export async function createSkill(payload) {
    const response = await fetch('/api/agent/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    return parseJsonResponse(response, '保存 skill 失败');
}

export async function updateSkill(skillId, payload) {
    const response = await fetch(`/api/agent/skills/${skillId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    return parseJsonResponse(response, '保存 skill 失败');
}

export async function deleteSkill(skillId) {
    const response = await fetch(`/api/agent/skills/${skillId}`, { method: 'DELETE' });
    if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '删除 skill 失败');
    }
}

export async function fetchSessions() {
    const response = await fetch('/api/sessions');
    return parseJsonResponse(response, '加载会话失败');
}

export async function fetchSessionDetail(sessionId) {
    const response = await fetch(`/api/sessions/${sessionId}`);
    return parseJsonResponse(response, '加载会话失败');
}

export async function deleteSession(sessionId) {
    const response = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
    if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '删除会话失败');
    }
}

export async function fetchArtifacts(sessionId) {
    const response = await fetch(`/api/sessions/${sessionId}/artifacts`);
    return parseJsonResponse(response, '加载文档失败');
}

export async function fetchArtifact(sessionId, artifactId) {
    const response = await fetch(`/api/sessions/${sessionId}/artifacts/${artifactId}`);
    return parseJsonResponse(response, '加载文档失败');
}

export async function saveArtifact(sessionId, payload, fallbackMessage) {
    const response = await fetch(`/api/sessions/${sessionId}/artifacts/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    return parseJsonResponse(response, fallbackMessage);
}

export async function cancelRun(runId) {
    const response = await fetch(`/api/runs/${runId}/cancel`, { method: 'POST' });
    if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '停止执行失败');
    }
}

export async function startAskStream(formData) {
    const response = await fetch('/api/ask/stream', {
        method: 'POST',
        body: formData,
    });
    if (!response.ok) {
        const text = await response.text();
        let detail = '请求失败';
        try {
            detail = JSON.parse(text).detail || detail;
        } catch {
            detail = text || detail;
        }
        throw new Error(detail);
    }
    return response;
}
