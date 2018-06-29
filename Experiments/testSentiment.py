from textblob import TextBlob
from textblob.classifiers import NaiveBayesClassifier

#review = TextBlob("are you sure about this loop, which does not run ;-)")
#print(review.sentiment)
with open("training_data.csv", "r") as fp:
    cl = NaiveBayesClassifier(fp, format="csv")
    review = """
 I understand the desire here to make the views cleaner, and this change makes sense in the context of the status field being used for personalization. But, with this applied, any utility that the field provides is essentially completely removed. Many users use this to notify people of their out-of-office/vacation status, for example. It's the reason this was implemented in the first place [1]. 

I think there's more nuance to this issue. Perhaps we could add a property to the chip to show/hide the status, and then hide it in places like the dashboard. Even better, perhaps you could add a preference to show/hide account statuses globally. Or, maybe we could add some sort of 1ch indicator/icon to the chip indicating there is a status, that is then shown on mouseover (similar to the can-rebase indicator in the change metadata).

As this change exists, though, we would be regressing on an issue and essentially removing a feature that many users rely on. 
             """
    sent = cl.classify(review)
    sent_prob = cl.prob_classify(review)
    print(sent)
    print(sent_prob.prob(sent))
