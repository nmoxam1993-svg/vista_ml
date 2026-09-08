/**
 * ChurnModelCallout.cls
 * Invocable Apex action called by Agentforce to score a single guard.
 * Makes a callout to the FastAPI churn model endpoint.
 *
 * Setup required:
 *   1. Setup > Named Credentials > New
 *      Name: Vista_ML_API
 *      URL:  https://your-api-url.railway.app
 *      Auth: No Authentication (or API Key header if you add auth)
 */
public class ChurnModelCallout {

    public class Request {
        @InvocableVariable(required=true label='Contact ID'
            description='Salesforce Contact ID of the guard to score')
        public Id contactId;
    }

    public class Result {
        @InvocableVariable(label='Churn Probability')
        public Decimal churnProbability;

        @InvocableVariable(label='Risk Tier')
        public String riskTier; // High / Medium / Low

        @InvocableVariable(label='Top Risk Factor')
        public String topRiskFactor;

        @InvocableVariable(label='Recommended Action')
        public String recommendedAction;

        @InvocableVariable(label='Success')
        public Boolean success;

        @InvocableVariable(label='Error Message')
        public String errorMessage;
    }

    @InvocableMethod(
        label='Score Guard Churn Risk (ML)'
        description='Calls LightGBM model API and returns churn probability for a guard'
        category='Vista Security'
    )
    public static List<Result> scoreGuard(List<Request> requests) {
        List<Result> results = new List<Result>();

        for (Request req : requests) {
            Result r = new Result();
            try {
                // Fetch guard + site features
                Contact g = [
                    SELECT  Id, Tenure_Days__c, Total_CallOffs__c,
                            Performance_Rating__c, Cross_Trained__c,
                            Float_Guard__c, Hourly_Rate__c,
                            Account.Site_Type__c, Account.Bill_Rate__c,
                            Account.Pay_Rate__c
                    FROM    Contact
                    WHERE   Id = :req.contactId
                    LIMIT   1
                ];

                // Build JSON payload matching FastAPI GuardFeatures schema
                Map<String,Object> payload = new Map<String,Object>{
                    'contact_id'         => String.valueOf(req.contactId),
                    'tenure_days'        => g.Tenure_Days__c        ?? 0,
                    'total_call_offs'    => g.Total_CallOffs__c      ?? 0,
                    'shift_calloffs'     => 0,
                    'performance_rating' => g.Performance_Rating__c  ?? 3.5,
                    'cross_trained'      => g.Cross_Trained__c       ?? false,
                    'float_guard'        => g.Float_Guard__c         ?? false,
                    'hourly_rate'        => g.Hourly_Rate__c         ?? 20,
                    'bill_rate'          => g.Account?.Bill_Rate__c  ?? 40,
                    'pay_rate'           => g.Account?.Pay_Rate__c   ?? 20,
                    'site_type'          => g.Account?.Site_Type__c  ?? 'Corporate',
                    'site_ot_pct'        => 0,
                    'site_calloffs'      => 0
                };

                HttpRequest req2 = new HttpRequest();
                req2.setEndpoint('callout:Vista_ML_API/predict/churn');
                req2.setMethod('POST');
                req2.setHeader('Content-Type', 'application/json');
                req2.setBody(JSON.serialize(payload));
                req2.setTimeout(10000);

                HttpResponse resp = new Http().send(req2);

                if (resp.getStatusCode() == 200) {
                    Map<String,Object> body =
                        (Map<String,Object>) JSON.deserializeUntyped(resp.getBody());

                    r.churnProbability  = (Decimal) body.get('churn_probability');
                    r.riskTier          = (String)  body.get('churn_tier');
                    r.topRiskFactor     = (String)  body.get('top_risk_factor');
                    r.recommendedAction = (String)  body.get('recommended_action');
                    r.success           = true;

                    // Write risk tier back to Contact immediately
                    update new Contact(
                        Id               = req.contactId,
                        Turnover_Risk__c = r.riskTier
                    );

                } else {
                    r.success      = false;
                    r.errorMessage = 'API returned HTTP ' + resp.getStatusCode();
                }
            } catch (Exception e) {
                r.success      = false;
                r.errorMessage = e.getMessage();
            }
            results.add(r);
        }
        return results;
    }
}
