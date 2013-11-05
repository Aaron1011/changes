define(['app', 'directives/radialProgressBar', 'directives/timeSince', 'directives/duration',
        'filters/escape', 'filters/wordwrap', 'modules/pagination'], function(app) {
  app.controller('buildDetailsCtrl', ['$scope', 'initialData', '$window', '$http', '$routeParams', 'stream', 'pagination', 'flash', function($scope, initialData, $window, $http, $routeParams, Stream, Pagination, flash) {
    'use strict';

    var stream,
        entrypoint = '/api/0/builds/' + $routeParams.build_id + '/';

    function getTestStatus() {
      if ($scope.build.status.id == "finished") {
        if ($scope.testGroups.length === 0) {
          return "no-results";
        } else {
          return "has-results";
        }
      }
      return "pending";
    }

    function updateBuild(data){
      $scope.$apply(function() {
        $scope.build = data;
      });
    }

    function addTest(data) {
      $scope.$apply(function() {
        var updated = false,
            item_id = data.id,
            attr, result, item;

        if (data.result.id != 'failed') {
          // we dont care about non-failures
          return;
        }

        if ($scope.testFailures.length > 0) {
          result = $.grep($scope.testFailures, function(e){ return e.id == item_id; });
          if (result.length > 0) {
            item = result[0];
            for (attr in data) {
              // ignore dateModified as we're updating this frequently and it causes
              // the dirty checking behavior in angular to respond poorly
              if (item[attr] != data[attr] && attr != 'dateModified') {
                updated = true;
                item[attr] = data[attr];
              }
              if (updated) {
                item.dateModified = data.dateModified;
              }
            }
          }
        }
        if (!updated) {
          $scope.testFailures.unshift(data);
        }
      });
    }

    function getChartData(builds) {
      // this should return two series, one with passes, and one with failures
      var ok = [],
          failures = [],
          build, point, i;

      for (i = 0; (build = builds[i]); i++) {
        point = [i, build.duration || 1];
        if (build.result.id == 'passed' || build.result.id == 'skipped') {
          ok.push(point);
        } else {
          failures.push(point)
        }
      }

      return {
        values: [
          {data: ok, color: '#c7c0de', label: 'Ok'},
          {data: failures, color: '#d9322d', label: 'Failed'}
        ]
      }
    }

    $scope.build = initialData.data.build;
    $scope.phases = initialData.data.phase;
    $scope.testFailures = initialData.data.testFailures;
    $scope.testGroups = initialData.data.testGroups;
    $scope.testStatus = getTestStatus();
    $scope.previousRuns = initialData.data.previousRuns
    $scope.chartData = getChartData($scope.previousRuns);

    $scope.$watch("build.status", function(status) {
      $scope.testStatus = getTestStatus();
    });
    $scope.$watch("tests", function(status) {
      $scope.testStatus = getTestStatus();
    });

    $scope.retryBuild = function() {
      $http.post('/api/0/builds/' + $scope.build.id + '/retry/')
        .success(function(data){
          $window.location.href = data.build.link;
        })
        .error(function(){
          flash('error', 'There was an error while retrying this build.');
        });
    };

    stream = Stream($scope, entrypoint);
    stream.subscribe('build.update', updateBuild);
    stream.subscribe('test.update', addTest);
  }]);
});
