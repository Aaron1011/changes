define([
    'app',
    'utils/chartHelpers',
    'utils/duration',
    'utils/escapeHtml',
    'directives/radialProgressBar',
    'directives/timeSince',
    'directives/duration',
    'filters/escape',
    'filters/wordwrap',
    'modules/pagination'], function(app, chartHelpers, duration, escapeHtml) {
  app.controller('buildDetailsCtrl', ['$scope', 'initialData', '$window', '$timeout', '$http', '$routeParams', 'stream', 'pagination', 'flash', function($scope, initialData, $window, $timeout, $http, $routeParams, Stream, Pagination, flash) {
    'use strict';

    var stream, logSources = {},
        entrypoint = '/api/0/builds/' + $routeParams.build_id + '/',
        chart_options = {
          tooltipFormatter: function(item) {
            var content = ''

            content += '<h5>';
            content += escapeHtml(item.name);
            content += '<br><small>';
            content += escapeHtml(item.target);
            if (item.author) {
              content += ' &mdash; ' + item.author.name;
            }
            content += '</small>'
            content += '</h5>';
            if (item.status.id == 'finished') {
              content += '<p>Build ' + item.result.name;
              if (item.duration) {
                content += ' in ' + duration(item.duration);
              }
              content += '</p>';
            } else {
              content += '<p>' + item.status.name + '</p>';
            }

            return content;
          }
        };

    function getLogSourceEntrypoint(logSource) {
      return '/api/0/builds/' + $scope.build.id + '/logs/' + logSource.id + '/';
    }

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

    function updateBuildLog(data) {
      // Angular isn't intelligent enough to optimize this.
      var el = $('#log-' + data.source.id),
          item, source_id = data.source.id;

      if (el.length === 0) {
        // logsource isnt available in viewpane
        return;
      }

      if (!logSources[source_id]) {
        logSources[source_id] = {
          text: '',
          nextOffset: null
        };
      }

      item = logSources[source_id];
      if (data.offset < item.nextOffset) {
        return;
      }

      // TODO(dcramer): we should only remove/append rows, rather
      // than rewriting the entire block
      item.text = (item.text + data.text).substr(-10000);
      item.nextOffset = data.offset + data.size;

      el.empty();
      $.each(item.text.split('\n'), function(_, line){
        el.append('<div class="line">' + line + '</div>');
      });
      $timeout(function(){
        el.scrollTop(el.height(), 100);
      });
    }

    function updateTestGroup(data) {
      $scope.$apply(function() {
        var updated = false,
            item_id = data.id,
            attr, result, item;

        // TODO(dcramer); we need to refactor all of this logic as its repeated in nealry
        // every stream
        if ($scope.testGroups.length > 0) {
          result = $.grep($scope.testGroups, function(e){ return e.id == item_id; });
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
          $scope.testGroups.unshift(data);
        }

        if (data.result.id == 'failed') {
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
        }
      });
    }

    $scope.retryBuild = function() {
      $http.post('/api/0/builds/' + $scope.build.id + '/retry/')
        .success(function(data){
          $window.location.href = data.build.link;
        })
        .error(function(){
          flash('error', 'There was an error while retrying this build.');
        });
    };

    $scope.build = initialData.data.build;
    $scope.logSources = initialData.data.logs;
    $scope.phases = initialData.data.phase;
    $scope.testFailures = initialData.data.testFailures;
    $scope.testGroups = initialData.data.testGroups;
    $scope.testStatus = getTestStatus();
    $scope.previousRuns = initialData.data.previousRuns
    $scope.chartData = chartHelpers.getChartData($scope.previousRuns, $scope.build, chart_options);

    $scope.$watch("build.status", function(status) {
      $scope.testStatus = getTestStatus();
    });
    $scope.$watch("tests", function(status) {
      $scope.testStatus = getTestStatus();
    });

    $.each($scope.logSources, function(_, logSource){
      $http.get(getLogSourceEntrypoint(logSource))
        .success(function(data){
          $.each(data.chunks, function(_, chunk){
            updateBuildLog(chunk);
          });
        });
    });

    // TODO: we need to support multiple soruces, a real-time stream, and real-time source changes
    stream = Stream($scope, entrypoint);
    stream.subscribe('build.update', updateBuild);
    stream.subscribe('buildlog.update', updateBuildLog);
    stream.subscribe('testgroup.update', updateTestGroup);
  }]);
});
