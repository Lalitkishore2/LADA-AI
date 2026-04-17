import type { ExecApprovalReplyDecision } from "lada/plugin-sdk/approval-runtime";
import type { LADAConfig } from "lada/plugin-sdk/config-runtime";
import { isApprovalNotFoundError } from "lada/plugin-sdk/error-runtime";
import { withOperatorApprovalsGatewayClient } from "lada/plugin-sdk/gateway-runtime";

export { isApprovalNotFoundError };

export async function resolveMatrixExecApproval(params: {
  cfg: LADAConfig;
  approvalId: string;
  decision: ExecApprovalReplyDecision;
  senderId?: string | null;
  gatewayUrl?: string;
}): Promise<void> {
  await withOperatorApprovalsGatewayClient(
    {
      config: params.cfg,
      gatewayUrl: params.gatewayUrl,
      clientDisplayName: `Matrix approval (${params.senderId?.trim() || "unknown"})`,
    },
    async (gatewayClient) => {
      await gatewayClient.request("exec.approval.resolve", {
        id: params.approvalId,
        decision: params.decision,
      });
    },
  );
}

