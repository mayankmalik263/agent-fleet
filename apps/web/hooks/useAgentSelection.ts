// Selected agent (graph and timeline highlight) and the agent open in the inspector.
import { useCallback, useState } from "react";

export function useAgentSelection() {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [inspectorAgentId, setInspectorAgentId] = useState<string | null>(null);

  /** Select an agent. With open = true the inspector opens too. null clears the selection. */
  const selectAgent = useCallback((agentId: string | null, open = false) => {
    setSelectedAgentId(agentId);
    if (open && agentId) setInspectorAgentId(agentId);
  }, []);

  const closeInspector = useCallback(() => setInspectorAgentId(null), []);

  return { selectedAgentId, inspectorAgentId, selectAgent, closeInspector };
}
