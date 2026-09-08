@isTest
public class ContractPricingEngineTest {

    @TestSetup
    static void makeData() {
        Account site = new Account(
            Name             = 'Delta Hospital Test',
            Site_Type__c     = 'Healthcare',
            Bill_Rate__c     = 35,
            Pay_Rate__c      = 26,
            Target_Margin__c = 25
        );
        insert site;

        // 3 months of underperforming data
        List<Monthly_Performance__c> mps = new List<Monthly_Performance__c>();
        for (Integer i = 0; i < 3; i++) {
            mps.add(new Monthly_Performance__c(
                Site__c            = site.Id,
                Month__c           = 'Test-0' + i,
                Month_Date__c      = Date.today().addMonths(-i),
                Actual_Margin__c   = 22.5,
                OT_Pct__c          = 18.0,
                Call_Offs__c       = 4,
                Revenue__c         = 9800,
                Cost__c            = 7595,
                Total_Hours__c     = 280
            ));
        }
        insert mps;
    }

    @isTest
    static void testUnderpricedSite() {
        Account site = [SELECT Id FROM Account LIMIT 1];

        ContractPricingEngine.Request req = new ContractPricingEngine.Request();
        req.accountId = site.Id;

        Test.startTest();
        List<ContractPricingEngine.Result> results =
            ContractPricingEngine.calculatePricing(
                new List<ContractPricingEngine.Request>{ req }
            );
        Test.stopTest();

        System.assertEquals(1, results.size());
        ContractPricingEngine.Result r = results[0];

        // At $35 bill / $26 pay with 25% target, should recommend increase
        System.assertEquals('Increase Rate', r.renewalRecommendation,
            'Healthcare at $35 is below target rate');
        System.assert(r.rateGap > 0, 'Rate gap should be positive (underpriced)');
        System.assert(r.breakEvenRate < r.targetBillRate, 
            'Break-even should be below target rate');
        System.assert(r.otSurcharge > 0, 
            'OT surcharge should be recommended at 18% OT');

        // Confirm Account fields were written back
        Account updated = [
            SELECT Breakeven_Rate__c, Target_Bill_Rate__c,
                   Rate_Gap__c, Renewal_Rec__c
            FROM   Account WHERE Id = :site.Id
        ];
        System.assertNotEquals(null, updated.Breakeven_Rate__c);
        System.assertEquals('Increase Rate', updated.Renewal_Rec__c);
    }
}
