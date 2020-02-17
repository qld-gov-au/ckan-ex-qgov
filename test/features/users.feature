@users
Feature: User APIs

    Scenario: Ensure user autocomplete is accessible to sysadmins
        Given "Admin" as the persona
        When I log in
        And I search the autocomplete API for user "admin"
        And I take a screenshot
        Then I should see an element with xpath "//*[contains(string(), '"name": "admin"')]"

    Scenario: Ensure user autocomplete is accessible to organisation admins
        Given "Group Admin" as the persona
        When I log in
        And I search the autocomplete API for user "admin"
        And I take a screenshot
        Then I should see an element with xpath "//*[contains(string(), '"name": "admin"')]"

    Scenario: Ensure user autocomplete is not accessible to non-admins
        Given "Publisher" as the persona
        When I log in
        And I search the autocomplete API for user "admin"
        And I take a screenshot
        Then I should see an element with xpath "//body//div[contains(string(), 'Internal server error')]"
        And I should not see an element with xpath "//*[contains(string(), '"name": "admin"')]"

    Scenario: Ensure user autocomplete is not accessible anonymously
        When I search the autocomplete API for user "admin"
        And I take a screenshot
        Then I should see an element with xpath "//body//div[contains(string(), 'Internal server error')]"
        And I should not see an element with xpath "//*[contains(string(), '"name": "admin"')]"


    Scenario: Ensure user list is accessible to sysadmins
        Given "Admin" as the persona
        When I log in
        And I go to the user list API
        And I take a screenshot
        Then I should see an element with xpath "//*[contains(string(), '"success": true,') and contains(string(), '"name": "admin"')]"

    Scenario: Ensure user list is accessible to organisation admins
        Given "Group Admin" as the persona
        When I log in
        And I go to the user list API
        And I take a screenshot
        Then I should see an element with xpath "//*[contains(string(), '"success": true,') and contains(string(), '"name": "admin"')]"

    Scenario: Ensure user_list is not accessible to non-admins
        Given "Publisher" as the persona
        When I log in
        And I go to the user list API
        And I take a screenshot
        Then I should see an element with xpath "//*[contains(string(), '"success": false,') and contains(string(), 'Authorization Error')]"

    Scenario: Ensure user_list is not accessible anonymously
        When I go to the user list API
        And I take a screenshot
        Then I should see an element with xpath "//*[contains(string(), '"success": false,') and contains(string(), 'requires an authenticated user')]"


    Scenario: Ensure user detail is accessible to sysadmins
        Given "Admin" as the persona
        When I log in
        And I go to the "admin" user API
        And I take a screenshot
        Then I should see an element with xpath "//*[contains(string(), '"success": true,') and contains(string(), '"name": "admin"')]"

    Scenario: Ensure user detail is accessible to organisation admins
        Given "Group Admin" as the persona
        When I log in
        And I go to the "group-admin" user API
        And I take a screenshot
        Then I should see an element with xpath "//*[contains(string(), '"success": true,') and contains(string(), '"name": "group-admin"')]"

    Scenario: Ensure user detail for self is accessible to non-admins
        Given "Publisher" as the persona
        When I log in
        And I go to the "publisher" user API
        And I take a screenshot
        Then I should see an element with xpath "//*[contains(string(), '"success": true,') and contains(string(), '"name": "publisher"')]"

    Scenario: Ensure non-self user detail is not accessible to non-admins
        Given "Publisher" as the persona
        When I log in
        And I go to the "admin" user API
        And I take a screenshot
        Then I should see an element with xpath "//*[contains(string(), '"success": false,') and contains(string(), 'Authorization Error')]"

    Scenario: Ensure user detail is not accessible anonymously
        When I go to the "publisher" user API
        And I take a screenshot
        Then I should see an element with xpath "//*[contains(string(), '"success": false,') and contains(string(), 'requires an authenticated user')]"
