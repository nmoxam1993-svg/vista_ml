@isTest
public class ChurnModelCalloutTest {

    // Mock HTTP response from the FastAPI model
    private class ChurnAPIMock implements HttpCalloutMock {
        public HttpResponse respond(HttpRequest req) {
            HttpResponse resp = new HttpResponse();
            resp.setStatusCode(200);
            resp.setBody('{'
                + '"contact_id":"003XX000001234",'
                + '"churn_probability":0.78,'
                + '"churn_tier":"High",'
                + '"top_risk_factor":"Short tenure (<90 days)",'
                + '"recommended_action":"Schedule check-in call within 2 weeks"'
                + '}');
            return resp;
        }
    }

    @TestSetup
    static void makeData() {
        Account site = new Account(
            Name             = 'Test Industrial Site',
            Site_Type__c     = 'Industrial',
            Bill_Rate__c     = 32,
            Pay_Rate__c      = 18,
            Target_Margin__c = 30
        );
        insert site;

        insert new Contact(
            FirstName            = 'John',
            LastName             = 'TestGuard',
            Email                = 'john.test@vistaops.com',
            AccountId            = site.Id,
            Employment_Status__c = 'Active',
            Hire_Date__c         = Date.today().addDays(-45),
            Tenure_Days__c       = 45,
            Total_CallOffs__c    = 6,
            Performance_Rating__c = 2.8,
            Cross_Trained__c     = false,
            Float_Guard__c       = false,
            Hourly_Rate__c       = 18
        );
    }

    @isTest
    static void testHighRiskGuard() {
        Contact g = [SELECT Id FROM Contact LIMIT 1];

        ChurnModelCallout.Request req = new ChurnModelCallout.Request();
        req.contactId = g.Id;

        Test.setMock(HttpCalloutMock.class, new ChurnAPIMock());

        Test.startTest();
        List<ChurnModelCallout.Result> results =
            ChurnModelCallout.scoreGuard(
                new List<ChurnModelCallout.Request>{ req }
            );
        Test.stopTest();

        System.assertEquals(1, results.size(), 'One result expected');
        System.assert(results[0].success, 'Should succeed');
        System.assertEquals('High', results[0].riskTier);
        System.assertEquals(0.78, results[0].churnProbability);

        // Confirm Contact was updated
        Contact updated = [SELECT Turnover_Risk__c FROM Contact WHERE Id = :g.Id];
        System.assertEquals('High', updated.Turnover_Risk__c,
            'Turnover_Risk__c should be written back');
    }

    @isTest
    static void testAPIFailure() {
        Contact g = [SELECT Id FROM Contact LIMIT 1];

        // Mock a 500 error
        Test.setMock(HttpCalloutMock.class, new HttpCalloutMock() {
            public HttpResponse respond(HttpRequest r) {
                HttpResponse resp = new HttpResponse();
                resp.setStatusCode(500);
                resp.setBody('Internal Server Error');
                return resp;
            }
        });

        ChurnModelCallout.Request req = new ChurnModelCallout.Request();
        req.contactId = g.Id;

        Test.startTest();
        List<ChurnModelCallout.Result> results =
            ChurnModelCallout.scoreGuard(
                new List<ChurnModelCallout.Request>{ req }
            );
        Test.stopTest();

        System.assert(!results[0].success, 'Should fail gracefully');
        System.assert(results[0].errorMessage != null, 'Error message should be set');
    }
}
