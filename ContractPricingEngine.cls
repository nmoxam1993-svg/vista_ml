/**
 * ContractPricingEngine.cls
 * Calculates break-even rate, target rate, rate gap, and
 * renewal recommendation for a site contract.
 * Called by Agentforce and by the RenewalAlertFlow.
 */
public class ContractPricingEngine {

    // Overhead factor: fixed costs per hour (admin, insurance, equipment)
    // Adjust based on Vista's actual overhead per guard hour
    private static final Decimal OVERHEAD_PER_HOUR = 2.50;

    public class Request {
        @InvocableVariable(required=true label='Account ID')
        public Id accountId;
    }

    public class Result {
        @InvocableVariable(label='Site Name')
        public String siteName;

        @InvocableVariable(label='Current Bill Rate')
        public Decimal currentBillRate;

        @InvocableVariable(label='Current Pay Rate')
        public Decimal currentPayRate;

        @InvocableVariable(label='Break Even Rate')
        public Decimal breakEvenRate;

        @InvocableVariable(label='Target Bill Rate')
        public Decimal targetBillRate;

        @InvocableVariable(label='Rate Gap')
        public Decimal rateGap; // positive = underpriced

        @InvocableVariable(label='OT Surcharge Recommended')
        public Decimal otSurcharge;

        @InvocableVariable(label='Renewal Recommendation')
        public String renewalRecommendation; // Increase / Hold / Room to Decrease

        @InvocableVariable(label='Contract Health Score')
        public Integer contractHealthScore; // 0-100

        @InvocableVariable(label='Negotiation Talking Points')
        public String talkingPoints;
    }

    @InvocableMethod(
        label='Calculate Contract Pricing'
        description='Returns break-even rate, target rate, rate gap and renewal recommendation for a site'
        category='Vista Security'
    )
    public static List<Result> calculatePricing(List<Request> requests) {
        List<Result> results = new List<Result>();

        for (Request req : requests) {
            Account site = [
                SELECT  Name, Bill_Rate__c, Pay_Rate__c,
                        Target_Margin__c, Site_Type__c
                FROM    Account
                WHERE   Id = :req.accountId
            ];

            // Last 3 months of performance
            List<Monthly_Performance__c> history = [
                SELECT  Actual_Margin__c, OT_Pct__c, Call_Offs__c,
                        Revenue__c, Cost__c, Total_Hours__c
                FROM    Monthly_Performance__c
                WHERE   Site__c = :req.accountId
                ORDER BY Month_Date__c DESC
                LIMIT   3
            ];

            Result r = new Result();
            r.siteName       = site.Name;
            r.currentBillRate = site.Bill_Rate__c;
            r.currentPayRate  = site.Pay_Rate__c;

            // Break-even = (pay_rate + overhead) / (1 - tiny margin to cover admin)
            // Minimum rate to avoid a loss at any OT level
            r.breakEvenRate = (site.Pay_Rate__c + OVERHEAD_PER_HOUR)
                .divide(1 - 0.02, 2); // 2% floor

            // Target rate = rate needed to hit Target_Margin
            r.targetBillRate = (site.Pay_Rate__c + OVERHEAD_PER_HOUR)
                .divide(1 - (site.Target_Margin__c / 100), 2);

            r.rateGap = r.targetBillRate - site.Bill_Rate__c;

            // OT surcharge: if avg OT > 15%, recommend a per-hour surcharge
            Decimal avgOtPct = 0;
            if (!history.isEmpty()) {
                Decimal sumOt = 0;
                for (Monthly_Performance__c mp : history) {
                    sumOt += mp.OT_Pct__c ?? 0;
                }
                avgOtPct = sumOt / history.size();
            }
            r.otSurcharge = avgOtPct > 15
                ? (site.Pay_Rate__c * 0.5 * (avgOtPct/100)).setScale(2)
                : 0;

            // Recommendation
            if      (r.rateGap > 2)   r.renewalRecommendation = 'Increase Rate';
            else if (r.rateGap < -3)  r.renewalRecommendation = 'Competitive Room';
            else                      r.renewalRecommendation = 'Hold';

            // Health score (0-100): margin weight 60, OT weight 25, calloffs 15
            Decimal avgMargin = 0;
            Decimal avgCalloffs = 0;
            if (!history.isEmpty()) {
                for (Monthly_Performance__c mp : history) {
                    avgMargin   += mp.Actual_Margin__c ?? 0;
                    avgCalloffs += mp.Call_Offs__c     ?? 0;
                }
                avgMargin   = avgMargin   / history.size();
                avgCalloffs = avgCalloffs / history.size();
            }
            Decimal marginScore   = Math.min((avgMargin / site.Target_Margin__c) * 60, 60);
            Decimal otScore       = Math.max(25 - (avgOtPct - 10) * 1.5, 0);
            Decimal calloffScore  = Math.max(15 - avgCalloffs * 2, 0);
            r.contractHealthScore = Integer.valueOf(
                (marginScore + otScore + calloffScore).setScale(0));

            // Talking points for renewal conversation
            List<String> points = new List<String>();
            if (r.rateGap > 0) {
                points.add('Current rate of $' + site.Bill_Rate__c
                    + '/hr is below the target rate of $'
                    + r.targetBillRate.setScale(2) + '/hr for this site type.');
            }
            if (avgOtPct > 15) {
                points.add('Average OT rate of ' + avgOtPct.setScale(1)
                    + '% adds $' + r.otSurcharge + '/hr in unrecovered costs.');
            }
            if (r.contractHealthScore >= 70) {
                points.add('This site has a health score of '
                    + r.contractHealthScore + '/100 — a strong performance record.');
            }
            r.talkingPoints = String.join(points, ' | ');

            // Write pricing fields back to the Account record
            update new Account(
                Id = req.accountId,
                Breakeven_Rate__c      = r.breakEvenRate,
                Target_Bill_Rate__c    = r.targetBillRate,
                Rate_Gap__c            = r.rateGap,
                OT_Surcharge__c        = r.otSurcharge,
                Renewal_Rec__c         = r.renewalRecommendation,
                Contract_Health_Score__c = r.contractHealthScore
            );

            results.add(r);
        }
        return results;
    }
}
