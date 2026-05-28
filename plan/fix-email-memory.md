# fix-email-memory

In the settings file kept by quicknxsv1 (in ~/.quicknxs/**) I observed this recently:

```
diff --git a/.quicknxs/reduction.ini b/.quicknxs/reduction.ini
index 23d63cc..3bef991 100644
--- a/.quicknxs/reduction.ini
+++ b/.quicknxs/reduction.ini
@@ -1,29 +1,29 @@
 [email]
     SendData = True
     Cc = ''
-    Text = 'Dear User,\n\nHere is the data extracted for the files {numbers}.\n\nRegards from beamline %(instrument.BEAMLINE)s'
-    To = '%(paths.USER)s@ornl.gov'
+    Text = 'Dear User,\n\nHere is the data extracted for the files {numbers}.\n\nRegards from beamline 4A'
+    To = 'bvacaliuc@ornl.gov'
     SendPlots = False
     SendAll = False
     ZIPData = True
-    Subject = 'SNS BL %(instrument.BEAMLINE)s extraction {ipts}'
+    Subject = 'SNS BL 4A extraction {ipts}'
```

Observe how the substitutions were hard coded? The 'To =' is in fact *wrong* on *this machine* (it is only correct on analysis.sns.gov). This should be fixed.
